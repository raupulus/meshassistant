from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import Optional

from Models.Database import Database
from Models.Api import Api
from Models.Aemet import Aemet
from functions import log_p
import env


def _parse_dt(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def _should_run(db: Database, name: str, min_interval_minutes: int) -> bool:
    last = _parse_dt(db.get_task_last_run(name))
    if not last:
        return True
    return datetime.now() - last >= timedelta(minutes=min_interval_minutes)


def chiste_upload() -> None:
    """Sube chistes con need_upload=True. Frecuencia: máxima 1/hora."""
    db = Database()
    task_name = 'chiste_upload'
    if not _should_run(db, task_name, 60):
        log_p(f"[cron] chiste_upload: omitido (cooldown 60min)")
        return

    api = Api()
    # Configurar API key específica para este endpoint si está definida
    api_key = getattr(env, 'CHISTES_API_KEY', None)
    if api_key:
        api.set_apikey(api_key)
    url = getattr(env, 'CHISTES_URL_UPLOAD', None)
    if not url:
        log_p("[cron] chiste_upload: CHISTES_URL_UPLOAD no configurado")
        return

    to_send = db.get_chistes_to_upload(limit=200)
    if not to_send:
        log_p("[cron] chiste_upload: no hay chistes para subir")
        db.set_task_run(task_name)
        return

    uploaded_ids = []
    errors = 0
    log_p(f"[cron] chiste_upload: intentando subir {len(to_send)} chistes → {url}")
    for item in to_send:
        payload = {
            'from': item.get('from'),
            'content': item.get('content'),
            'id_local': item.get('id'),
        }
        try:
            resp = api.upload(url, payload)
            # Asumimos éxito si no lanza excepción; si la API devuelve ok, mejor
            if isinstance(resp, dict) and ('ok' in resp) and not resp.get('ok'):
                log_p(f"[cron] chiste_upload: respuesta no OK para id={item['id']}: {resp}", level="WARN")
                continue
            uploaded_ids.append(item['id'])
        except Exception as e:
            # continuar con el siguiente
            errors += 1
            log_p(f"[cron] chiste_upload: error subiendo id={item['id']}: {e}", level="WARN")
            continue

    if uploaded_ids:
        db.mark_chistes_uploaded(uploaded_ids)
        log_p(f"[cron] chiste_upload: subidos y marcados {len(uploaded_ids)}; errores {errors}")
    else:
        log_p(f"[cron] chiste_upload: nada subido; errores {errors}")
    db.set_task_run(task_name)


def chiste_download() -> None:
    """Descarga chistes nuevos desde la API. Frecuencia: máxima 1/hora."""
    db = Database()
    task_name = 'chiste_download'
    if not _should_run(db, task_name, 60):
        log_p(f"[cron] chiste_download: omitido (cooldown 60min)")
        return

    api = Api()
    # Configurar API key específica para este endpoint si está definida
    api_key = getattr(env, 'CHISTES_API_KEY', None)
    if api_key:
        api.set_apikey(api_key)
    url = getattr(env, 'CHISTES_URL_DOWNLOAD', None)
    if not url:
        log_p("[cron] chiste_download: CHISTES_URL_DOWNLOAD no configurado")
        return

    last_id = db.get_last_downloaded_chiste_id()
    log_p(f"[cron] chiste_download: solicitando desde last_id={last_id} → {url}")
    payload = {'last_id': last_id}
    try:
        data = api.download(url, payload)
        if isinstance(data, dict) and 'items' in data:
            items = data['items']
        elif isinstance(data, list):
            items = data
        else:
            items = []
        inserted, ignored = db.bulk_insert_api_chistes(items)
        log_p(f"[cron] chiste_download: recibidos {len(items)} → insertados {inserted}, ignorados {ignored}")
    except Exception as e:
        # ignorar errores de red momentáneos
        log_p(f"[cron] chiste_download: error descargando: {e}", level="WARN")
    finally:
        db.set_task_run(task_name)


def send_trace() -> None:
    """Encola la ejecución de un traceroute para que lo procese el proceso principal.

    Restricciones:
    - Throttle global: 1 intento cada TRACES_INTERVAL minutos medido con traces.updated_at del último procesado
    - Ventanas por nodo configurables: TRACES_RELOAD_INTERVAL (éxito) y TRACES_RETRY_INTERVAL (error)
    """
    # Permitir deshabilitar traces por configuración
    if not getattr(env, 'ENABLE_TRACES', False):
        log_p("[cron] send_trace: deshabilitado por ENABLE_TRACES=False")
        return

    db = Database()

    # Throttle global 5 minutos basado en el último trace realizado (updated_at)
    last_done_iso = db.get_last_trace_updated_at()
    log_p(f"[cron] send_trace: last_done={last_done_iso}")
    interval_min = int(getattr(env, 'TRACES_INTERVAL', 5) or 5)
    if last_done_iso:
        try:
            last_dt = datetime.fromisoformat(last_done_iso)
            if datetime.now() - last_dt < timedelta(minutes=interval_min):
                log_p(f"[cron] send_trace: omitido (cooldown global {interval_min}min)")
                return
        except Exception:
            pass

    # Seleccionar próximo nodo candidato respetando configuración
    hops_limit = int(getattr(env, 'TRACES_HOPS', 2) or 2)
    reload_hours = int(getattr(env, 'TRACES_RELOAD_INTERVAL', 24 * 7) or (24 * 7))
    retry_hours = int(getattr(env, 'TRACES_RETRY_INTERVAL', 24) or 24)

    node_id = db.get_next_node_to_trace(
        hops_limit=hops_limit,
        reload_hours=reload_hours,
        retry_hours=retry_hours,
    )
    if node_id:
        # Encolar petición en la propia tabla traces (status='pending')
        trace_id = db.enqueue_trace(node_id)
        log_p(f"[cron] send_trace: encolado trace id={trace_id} para nodo {node_id}")
    else:
        log_p(f"[cron] send_trace: ningún nodo candidato (≤{hops_limit} hops, no MQTT, ventanas cumplidas)")


def check_aemet() -> None:
    """Descarga alertas de AEMET (si hay API key) y las guarda en BD (tabla aemet).

    - Ejecutar como máximo 1 vez por hora.
    - Solo se usa si hay AEMET_API_KEY configurada.
    - La publicación se hace en el proceso principal (loop) para minimizar lógica aquí.
    """
    db = Database()
    task_name = 'aemet_fetch'
    # Ejecutar como mucho cada hora
    if not _should_run(db, task_name, 60):
        log_p("[cron] check_aemet: omitido (cooldown 60min)")
        return

    # Solo si hay API key configurada
    if not getattr(env, 'AEMET_API_KEY', None):
        log_p("[cron] check_aemet: AEMET_API_KEY vacío; no se consulta API")
        db.set_task_run(task_name)
        return

    aemet = Aemet()
    log_p(f"[cron] check_aemet: provincia='{aemet.province}' canales={aemet.channels} periodo={aemet.period}")
    try:
        # One-shot: arreglar filas antiguas que guardaron XML crudo
        try:
            _aemet_fix_legacy_once()
        except Exception as e:
            log_p(f"[cron] check_aemet: fixer legacy error: {e}", level="WARN")

        texts: list[str] = []
        # Nueva vía oficial para provincias: endpoint de archivo por rango temporal (tar.gz con XMLs)
        try:
            texts = fetch_aemet_alerts_archive(aemet)
        except Exception as e:
            log_p(f"[cron] check_aemet: error en fetch-archivo: {e}", level="WARN")
            texts = []

        # Fallback opcional: intentar endpoints anteriores (áreas/CCAA o base general)
        if not texts:
            try:
                texts = fetch_aemet_alerts_for_province(aemet)
            except Exception as e:
                log_p(f"[cron] check_aemet: error en fetch-province: {e}", level="WARN")
                texts = []

        if texts:
            inserted, ignored = db.aemet_bulk_insert(aemet.province, texts)
            log_p(f"[cron] check_aemet: descargadas {len(texts)} → insertadas {inserted}, ignoradas {ignored}")
        else:
            log_p("[cron] check_aemet: sin contenido recibido")
    except Exception as e:
        # Ignorar errores temporales
        log_p(f"[cron] check_aemet: excepción general: {e}", level="WARN")
    finally:
        db.set_task_run(task_name)


def _aemet_fix_legacy_once() -> None:
    """Ejecuta una migración de saneado AEMET solo una vez.

    Convierte filas antiguas que tengan XML crudo en data_raw/message a texto en español.
    """
    db = Database()
    mark = 'aemet_fix_legacy_done'
    if db.get_task_last_run(mark):
        return
    processed, updated, deleted = db.aemet_fix_legacy_rows(limit=5000)
    log_p(f"[cron] aemet_fix_legacy_once: procesadas={processed}, actualizadas={updated}, eliminadas={deleted}")
    db.set_task_run(mark)


def fetch_aemet_alerts_for_province(aemet: Aemet) -> list[str]:
    """Obtiene alertas desde OpenData de AEMET siguiendo la especificación oficial.

    Flujo correcto (dos pasos):
    1) GET al endpoint `.../opendata/api/avisos_cap/ultimoelaborado[/provincia/{X}|/area/{Y}]?api_key=...`
       Devuelve JSON con campos `estado`, `datos`, `metadatos`.
    2) GET a la URL de `datos` (sin api_key) y devolver el contenido (normalmente XML/Texto).

    Devuelve una lista con el/los textos descargados. Vacía si no hay datos.
    """
    import requests
    import unicodedata
    from urllib.parse import quote

    log_p("[cron] fetch_aemet: iniciando descarga")

    # Solo cabeceras básicas; la api_key va en query (paso 1)
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }

    api_key = getattr(aemet, 'api_key', None)
    prov_raw = (aemet.province or '').strip()

    def _normalize_name(s: str) -> str:
        # Quitar acentos, colapsar espacios, mayúsculas
        nfkd = unicodedata.normalize('NFKD', s)
        s2 = ''.join([c for c in nfkd if not unicodedata.combining(c)])
        return ' '.join(s2.split()).upper()

    prov_norm = _normalize_name(prov_raw) if prov_raw else ''
    prov_title = prov_raw.title() if prov_raw else ''

    # Determinar orden de prueba: para Galicia probamos AREA primero; para Cádiz, PROVINCIA
    AREA_NAMES = {
        "GALICIA", "ANDALUCIA", "ARAGON", "ASTURIAS", "BALEARES", "CANARIAS", "CANTABRIA",
        "CASTILLA Y LEON", "CASTILLA-LA MANCHA", "CATALUNA", "CEUTA", "EXTREMADURA",
        "LA RIOJA", "MADRID", "MELILLA", "MURCIA", "NAVARRA", "PAIS VASCO", "COMUNITAT VALENCIANA"
    }

    # Endpoints oficiales según documentación:
    # - Filtrado por provincia/área (singular):  .../avisos_cap/ultimoelaborado
    #   Subrutas: /provincia/{codigoINEdosDigitos} | /area/{NOMBRE_AREA}
    # - Sin filtro (plural):                      .../avisos_cap/ultimoselaborados
    base_filter = 'https://opendata.aemet.es/opendata/api/avisos_cap/ultimoelaborado'
    base_list = 'https://opendata.aemet.es/opendata/api/avisos_cap/ultimoselaborados'

    endpoints: list[str] = []
    if prov_norm:
        # Mapa nombre provincia -> código oficial AEMET (dos dígitos INE)
        PROV_NAME_TO_CODE = {
            "ALAVA": "01", "ARABA": "01", "ALBACETE": "02", "ALICANTE": "03", "ALACANT": "03",
            "ALMERIA": "04", "AVILA": "05", "BADAJOZ": "06", "BALEARES": "07", "ISLAS BALEARES": "07",
            "BARCELONA": "08", "BURGOS": "09", "CACERES": "10", "CADIZ": "11",
            "CASTELLON": "12", "CASTELLO": "12", "CIUDAD REAL": "13", "CORDOBA": "14", "A CORUNA": "15",
            "CORUNA": "15", "A CORUÑA": "15", "CUENCA": "16", "GIRONA": "17", "GERONA": "17", "GRANADA": "18",
            "GUADALAJARA": "19", "GUIPUZCOA": "20", "GIPUZKOA": "20", "HUELVA": "21", "HUESCA": "22",
            "JAEN": "23", "LEON": "24", "LERIDA": "25", "LLEIDA": "25", "LA RIOJA": "26",
            "LUGO": "27", "MADRID": "28", "MALAGA": "29", "MURCIA": "30", "NAVARRA": "31",
            "OURENSE": "32", "PALENCIA": "34", "LAS PALMAS": "35", "PONTEVEDRA": "36",
            "SALAMANCA": "37", "SANTA CRUZ DE TENERIFE": "38", "SEGOVIA": "40", "SEVILLA": "41",
            "SORIA": "42", "TARRAGONA": "43", "TERUEL": "44", "TOLEDO": "45", "VALENCIA": "46",
            "VALLADOLID": "47", "VIZCAYA": "48", "BIZKAIA": "48", "ZAMORA": "49", "ZARAGOZA": "50",
            "CEUTA": "51", "MELILLA": "52"
        }

        # Mapa CCAA (área) -> lista de códigos INE de provincias (para fallback)
        AREA_TO_PROV_CODES = {
            "GALICIA": ["15", "27", "32", "36"],  # A Coruña, Lugo, Ourense, Pontevedra
            # Se pueden añadir más CCAA si es necesario
        }

        # Si es una CCAA conocida, usar /area únicamente
        if prov_norm in AREA_NAMES:
            # Probar varias variantes de nombre de área
            for area_name in [prov_norm, prov_title, prov_raw]:
                if area_name:
                    endpoints.append(f"{base_filter}/area/{quote(area_name)}")
            # Fallback: si área falla, probar por provincias que componen esa CCAA
            for code in AREA_TO_PROV_CODES.get(prov_norm, []):
                endpoints.append(f"{base_filter}/provincia/{quote(code)}")
        else:
            # Provincias: permitir código directo (dos dígitos) o mapear nombre a código
            if prov_norm.isdigit() and len(prov_norm) in (2,):
                endpoints.append(f"{base_filter}/provincia/{quote(prov_norm)}")
            else:
                code = PROV_NAME_TO_CODE.get(prov_norm)
                if code:
                    endpoints.append(f"{base_filter}/provincia/{quote(code)}")
                else:
                    # Último recurso: intentar área con distintas variantes de nombre
                    for area_name in [prov_norm, prov_title, prov_raw]:
                        if area_name:
                            endpoints.append(f"{base_filter}/area/{quote(area_name)}")
    # Fallback sin filtro (plural) siempre al final
    endpoints.append(base_filter)  # singular sin filtro
    endpoints.append(base_list)    # plural sin filtro

    for url in endpoints:
        try:
            params = {'api_key': api_key} if api_key else None
            # Algunos despliegues aceptan api_key en cabecera; incluimos ambas formas
            req_headers = {'Accept': 'application/json'}
            if api_key:
                req_headers['api_key'] = api_key
            log_p(f"[cron] fetch_aemet: GET {url} params={bool(params)}")
            r1 = requests.get(url, headers=req_headers, params=params, timeout=5)
            ct1 = (r1.headers.get('Content-Type') or '').lower()
            log_p(f"[cron] fetch_aemet: resp1 status={r1.status_code} ct={ct1}")
            r1.raise_for_status()

            # Intentar JSON de control (estado/datos)
            j = None
            if 'json' in ct1:
                try:
                    j = r1.json()
                except Exception:
                    j = None

            if isinstance(j, dict):
                estado = j.get('estado')
                if estado is not None and int(str(estado)) != 200:
                    # Error reportado por AEMET en JSON de control
                    log_p(f"[cron] fetch_aemet: paso1 estado={estado} desc={j.get('descripcion')} (descartado)", level="WARN")
                    continue
                datos_url = j.get('datos')
                if not datos_url:
                    log_p("[cron] fetch_aemet: paso1 JSON sin 'datos' (descartado)", level="WARN")
                    continue
                # Segunda petición a 'datos' (documento real)
                log_p(f"[cron] fetch_aemet: GET datos {datos_url}")
                r2 = requests.get(datos_url, timeout=5)
                ct2 = (r2.headers.get('Content-Type') or '').lower()
                log_p(f"[cron] fetch_aemet: resp2 status={r2.status_code} ct={ct2}")
                r2.raise_for_status()
                # Si curiosamente devuelve JSON, validar que no sea error
                txt2 = r2.text.strip()
                if 'json' in ct2:
                    try:
                        j2 = r2.json()
                        est2 = j2.get('estado')
                        if est2 is not None and int(str(est2)) != 200:
                            log_p(f"[cron] fetch_aemet: paso2 estado={est2} desc={j2.get('descripcion')} (descartado)", level="WARN")
                            continue
                    except Exception:
                        # JSON inválido; lo tratamos como texto
                        pass
                log_p(f"[cron] fetch_aemet: datos len={len(txt2)}")
                if txt2:
                    return [txt2]
                else:
                    continue

            # Si no es JSON en paso 1 y no hay 'datos', aceptar solo si no es JSON y hay texto (poco probable)
            if 'json' not in ct1:
                txt_direct = r1.text.strip()
                log_p(f"[cron] fetch_aemet: respuesta directa len={len(txt_direct)} (ct={ct1})")
                if txt_direct:
                    return [txt_direct]
                else:
                    continue

            # Si llega aquí con JSON pero sin campo 'datos', descartar
            log_p("[cron] fetch_aemet: JSON recibido sin 'datos' (descartado)", level="WARN")
            continue

        except Exception as e:
            log_p(f"[cron] fetch_aemet: error con url {url}: {e}", level="WARN")
            continue
    return []


def fetch_aemet_alerts_archive(aemet: Aemet) -> list[str]:
    """Obtiene alertas CAP desde el endpoint de ARCHIVO por rango temporal (tar.gz) y filtra por provincia.

    Flujo:
      1) GET https://opendata.aemet.es/opendata/api/avisos_cap/archivo/fechaini/{UTC}/fechafin/{UTC}?api_key=...
         → JSON { estado, datos, metadatos }
      2) GET a 'datos' (tar.gz) → contiene múltiples .gz (cada uno con un XML CAP)
      3) Descomprimir y filtrar por provincia (`AEMET_PROVINCE`).

    Filtro por provincia:
      - Si AEMET_PROVINCE es una CCAA conocida (ej. Galicia), se filtra por nombres de sus provincias.
      - Si es una provincia, se filtra por su nombre normalizado dentro del XML (búsqueda textual).
    """
    import requests
    import io
    import tarfile
    import gzip as _gzip
    import unicodedata
    from urllib.parse import quote
    from datetime import datetime, timedelta, timezone

    api_key = getattr(aemet, 'api_key', None)
    prov_raw = (aemet.province or '').strip()

    def _normalize(s: str) -> str:
        nfkd = unicodedata.normalize('NFKD', s)
        s2 = ''.join([c for c in nfkd if not unicodedata.combining(c)])
        return ' '.join(s2.split()).upper()

    prov_norm = _normalize(prov_raw) if prov_raw else ''

    # Mapas auxiliares para Galicia (puedes ampliar si necesitas otras CCAA)
    AREA_TO_PROVINCE_NAMES = {
        'GALICIA': ['A CORUÑA', 'LUGO', 'OURENSE', 'PONTEVEDRA', 'GALICIA'],
    }

    # Rango temporal: desde hoy 00:00 UTC hasta mañana 00:00 UTC
    now_utc = datetime.now(timezone.utc)
    start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=2)  # cubre hoy y mañana (similar a ejemplo)

    def fmt(dt: datetime) -> str:
        # Formato requerido: YYYY-MM-DDTHH:MM:SSUTC (URL-encoded)
        return quote(dt.strftime('%Y-%m-%dT%H:%M:%S') + 'UTC', safe='')

    base = 'https://opendata.aemet.es/opendata/api/avisos_cap/archivo'
    url = f"{base}/fechaini/{fmt(start)}/fechafin/{fmt(end)}"

    params = {'api_key': api_key} if api_key else None
    log_p(f"[cron] fetch_aemet-archivo: GET {url} params={bool(params)}")
    r1 = requests.get(url, headers={'Accept': 'application/json'}, params=params, timeout=10)
    ct1 = (r1.headers.get('Content-Type') or '').lower()
    log_p(f"[cron] fetch_aemet-archivo: resp1 status={r1.status_code} ct={ct1}")
    r1.raise_for_status()

    j = r1.json()
    estado = j.get('estado') if isinstance(j, dict) else None
    if estado is None or int(str(estado)) != 200:
        desc = j.get('descripcion') if isinstance(j, dict) else None
        log_p(f"[cron] fetch_aemet-archivo: estado={estado} desc={desc} (descartado)", level='WARN')
        return []
    datos_url = j.get('datos')
    if not datos_url:
        log_p("[cron] fetch_aemet-archivo: paso1 JSON sin 'datos' (descartado)", level='WARN')
        return []

    # Descargar tar.gz con los avisos
    log_p(f"[cron] fetch_aemet-archivo: GET datos {datos_url}")
    r2 = requests.get(datos_url, timeout=20)
    ct2 = (r2.headers.get('Content-Type') or '').lower()
    log_p(f"[cron] fetch_aemet-archivo: resp2 status={r2.status_code} ct={ct2}")
    r2.raise_for_status()

    # Abrir tar (comprimido o no). Algunos despliegues devuelven TAR sin gzip.
    bio = io.BytesIO(r2.content)
    texts: list[str] = []

    with tarfile.open(fileobj=bio, mode='r:*') as tar:
        members = tar.getmembers()
        log_p(f"[cron] fetch_aemet-archivo: tar members={len(members)}")

        # Preparar lista de patrones de filtro
        targets: list[str] = []
        if prov_norm in AREA_TO_PROVINCE_NAMES:
            targets = [ _normalize(x) for x in AREA_TO_PROVINCE_NAMES[prov_norm] ]
        elif prov_norm:
            targets = [prov_norm]

        matched = 0
        scanned = 0
        for m in members:
            if not m.isfile():
                continue
            # cada entrada es a su vez .gz (contiene XML)
            f = tar.extractfile(m)
            if not f:
                continue
            try:
                file_bytes = f.read()
                xml_text = ''
                # Detectar por extensión o por cabecera gzip (0x1f, 0x8b)
                is_gz = m.name.lower().endswith('.gz') or (len(file_bytes) >= 2 and file_bytes[0] == 0x1F and file_bytes[1] == 0x8B)
                if is_gz:
                    try:
                        xml_bytes = _gzip.decompress(file_bytes)
                        try:
                            xml_text = xml_bytes.decode('utf-8', errors='replace').strip()
                        except Exception:
                            xml_text = xml_bytes.decode('latin-1', errors='replace').strip()
                    except Exception:
                        # Si falla la descompresión, tratar como texto directo
                        try:
                            xml_text = file_bytes.decode('utf-8', errors='replace').strip()
                        except Exception:
                            xml_text = file_bytes.decode('latin-1', errors='replace').strip()
                else:
                    # No es gz: leer como texto directo
                    try:
                        xml_text = file_bytes.decode('utf-8', errors='replace').strip()
                    except Exception:
                        xml_text = file_bytes.decode('latin-1', errors='replace').strip()
            except Exception:
                continue
            finally:
                try:
                    f.close()
                except Exception:
                    pass

            scanned += 1
            if not xml_text:
                continue

            if not targets:
                # sin filtro, aceptar todos
                texts.append(xml_text)
                matched += 1
                continue

            # filtro por presencia textual de provincia/área en el XML (normalizado)
            xml_norm = _normalize(xml_text)
            if any(t in xml_norm for t in targets):
                texts.append(xml_text)
                matched += 1

        log_p(f"[cron] fetch_aemet-archivo: filtrados {matched}/{scanned} elementos")

    return texts


def run_all():
    """Ejecuta todas las tareas con sus restricciones.

    Pensado para llamarse desde cron cada minuto.
    """
    log_p("[cron] run_all: inicio")
    chiste_upload()
    chiste_download()
    send_trace()
    check_aemet()
    log_p("[cron] run_all: fin")


if __name__ == '__main__':
    run_all()