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
    """Sube chistes con need_upload=True. Frecuencia: máxima 5/minutos."""
    db = Database()
    task_name = 'chiste_upload'

    if not _should_run(db, task_name, 5):
        log_p(f"[cron] chiste_upload: omitido (cooldown 5min)")
        return

    url = getattr(env, 'CHISTES_URL_UPLOAD', None)
    if not url:
        log_p("[cron] chiste_upload: CHISTES_URL_UPLOAD no configurado")
        db.set_task_run(task_name)
        return

    api = Api()
    # Configurar API key si existe (Bearer token)
    api_key = getattr(env, 'CHISTES_API_KEY', None)
    if api_key:
        api.set_apikey(api_key)

    to_send = db.get_chistes_to_upload(limit=5)
    if not to_send:
        log_p("[cron] chiste_upload: no hay chistes para subir")
        db.set_task_run(task_name)
        return

    uploaded_ids = []
    errors = 0
    log_p(f"[cron] chiste_upload: intentando subir {len(to_send)} chistes → {url}")
    for item in to_send:
        payload = {
            'nick': item.get('from'),
            'title': None,
            'content': item.get('content'),
        }
        try:
            resp = api.upload(url, payload)
            # La API devuelve success: true según el patrón visto en descarga
            if isinstance(resp, dict) and resp.get('success') is False:
                log_p(f"[cron] chiste_upload: respuesta error para id={item['id']}: {resp}", level="WARN")
                errors += 1
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

    if not _should_run(db, task_name, 10):
        log_p(f"[cron] chiste_download: omitido (cooldown 10min)")
        return

    url = getattr(env, 'CHISTES_URL_DOWNLOAD', None)
    if not url:
        log_p("[cron] chiste_download: CHISTES_URL_DOWNLOAD no configurado")
        db.set_task_run(task_name)
        return

    api = Api()
    # Configurar API key si existe (Bearer token)
    api_key = getattr(env, 'CHISTES_API_KEY', None)
    if api_key:
        api.set_apikey(api_key)

    last_id = db.get_last_downloaded_chiste_id()
    params = {
        'limit': 25,
        'after_id': last_id if last_id is not None else 0
    }
    exclude_groups = getattr(env, 'CHISTES_EXCLUDE_GROUPS', [3])
    data_payload = {
        'exclude_groups': exclude_groups
    }
    log_p(f"[cron] chiste_download: solicitando desde after_id={params['after_id']} → {url}")

    try:
        data = api.download(url, params=params, data=data_payload)
        if isinstance(data, dict) and data.get('success') is True:
            items = data.get('data', [])
            inserted, ignored = db.bulk_insert_api_chistes(items)
            log_p(f"[cron] chiste_download: recibidos {len(items)} → insertados {inserted}, ignorados {ignored}")
        else:
            log_p(f"[cron] chiste_download: respuesta inesperada o error en API: {data}", level="WARN")
    except Exception as e:
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

    # Seleccionar próximo nodo candidato respetando configuración y prioridad a routers cada 6h
    hops_limit = int(getattr(env, 'TRACES_HOPS', 2) or 2)
    reload_hours = int(getattr(env, 'TRACES_RELOAD_INTERVAL', 72) or 72)
    router_reload_hours = int(getattr(env, 'ROUTER_TRACE_INTERVAL_HOURS', 6) or 6)
    retry_hours = int(getattr(env, 'TRACES_RETRY_INTERVAL', 24) or 24)

    routers_cfg = getattr(env, 'ROUTER_NODES', None) or getattr(env, 'ROUTERS_LIST', None) or []
    if isinstance(routers_cfg, str):
        routers_cfg = [r.strip() for r in routers_cfg.split(',') if r.strip()]

    node_id = db.get_next_node_to_trace(
        hops_limit=hops_limit,
        reload_hours=reload_hours,
        router_reload_hours=router_reload_hours,
        retry_hours=retry_hours,
        router_identifiers=routers_cfg,
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

    # El cooldown de descarga debe alinearse con AEMET_PERIOD (no fijo a 60 min).
    # Reutilizamos el helper ya existente para traducir el periodo a minutos.
    aemet = Aemet()
    period_min = aemet.period_to_minutes(aemet.period)

    if not _should_run(db, task_name, period_min):
        log_p(f"[cron] check_aemet: omitido (cooldown {period_min}min)")
        return

    # Solo si hay API key configurada
    if not getattr(env, 'AEMET_API_KEY', None):
        log_p("[cron] check_aemet: AEMET_API_KEY vacío; no se consulta API")
        db.set_task_run(task_name)
        return

    log_p(f"[cron] check_aemet: provincia='{aemet.province}' canales={aemet.channels} periodo={aemet.period}")
    try:
        # One-shot: arreglar filas antiguas que guardaron XML crudo
        try:
            _aemet_fix_legacy_once()
        except Exception as e:
            log_p(f"[cron] check_aemet: fixer legacy error: {e}", level="WARN")

        # Priorizar el endpoint provincial, que ya filtra por provincia correctamente.
        # Solo usar el archivo (que requiere filtrado textual imperfecto) si falla.
        texts: Optional[list[str]] = None
        try:
            texts = fetch_aemet_alerts_for_province(aemet)
        except Exception as e:
            log_p(f"[cron] check_aemet: error en fetch-province: {e}", level="WARN")
            texts = None

        # Fallback al archivo solo si el endpoint provincial falló
        if texts is None:
            try:
                texts = fetch_aemet_alerts_archive(aemet)
            except Exception as e:
                log_p(f"[cron] check_aemet: error en fetch-archivo: {e}", level="WARN")
                texts = []

        if texts:
            inserted, ignored = db.aemet_bulk_insert(aemet.province, texts)
            log_p(f"[cron] check_aemet: descargadas {len(texts)} → insertadas {inserted}, ignoradas {ignored}")
        else:
            log_p("[cron] check_aemet: sin alertas para la provincia")
    except Exception as e:
        # Ignorar errores temporales
        log_p(f"[cron] check_aemet: excepción general: {e}", level="WARN")
    finally:
        db.set_task_run(task_name)


def weather_aemet() -> None:
    """Descarga la predicción meteorológica (clima) y la guarda como histórico.

    - Cadencia: según AEMET_PERIOD (mismo helper que el resto de AEMET).
    - Solo si hay AEMET_API_KEY configurada.
    - Prioriza el texto general de la PROVINCIA (AEMET_PROVINCE). Si la API no lo
      devuelve, hace fallback a la predicción del municipio (AEMET_CITY).
    - Guarda en la tabla `aemet_weather` para que /weather lo sirva offline.
    """
    db = Database()
    task_name = 'aemet_weather_fetch'

    aemet = Aemet()
    period_min = aemet.period_to_minutes(aemet.period)

    if not _should_run(db, task_name, period_min):
        log_p(f"[cron] weather_aemet: omitido (cooldown {period_min}min)")
        return

    if not getattr(env, 'AEMET_API_KEY', None):
        log_p("[cron] weather_aemet: AEMET_API_KEY vacío; no se consulta API")
        db.set_task_run(task_name)
        return

    try:
        prov_code = aemet.province_code()
        log_p(f"[cron] weather_aemet: provincia='{aemet.province}' code={prov_code} ciudad='{aemet.city}'")

        # 1) Vía principal: predicción general de la provincia (texto)
        text = None
        try:
            text = aemet.fetch_province_forecast(day='hoy')
        except Exception as e:
            log_p(f"[cron] weather_aemet: error provincia: {e}", level="WARN")

        if text:
            new_id = db.aemet_weather_insert(
                scope='province',
                content=text,
                province=aemet.province,
                province_code=prov_code,
                day='hoy',
                data_raw=text,
            )
            log_p(f"[cron] weather_aemet: provincia guardada id={new_id} len={len(text)}")
            db.set_task_run(task_name)
            return

        # 2) Fallback: predicción del municipio (AEMET_CITY)
        log_p("[cron] weather_aemet: sin texto de provincia; probando municipio")
        city_text = None
        try:
            city_text = aemet.fetch_city_forecast()
        except Exception as e:
            log_p(f"[cron] weather_aemet: error municipio: {e}", level="WARN")

        if city_text:
            new_id = db.aemet_weather_insert(
                scope='city',
                content=city_text,
                province=aemet.province,
                province_code=prov_code,
                city=aemet.city,
                city_code=aemet.resolve_city_code(),
                day='hoy',
                data_raw=city_text,
            )
            log_p(f"[cron] weather_aemet: municipio guardado id={new_id} len={len(city_text)}")
        else:
            log_p("[cron] weather_aemet: sin datos de provincia ni municipio")
    except Exception as e:
        log_p(f"[cron] weather_aemet: excepción general: {e}", level="WARN")
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


def extract_xmls_from_bytes(data: bytes, depth: int = 0) -> list[str]:
    """Extrae recursivamente textos XML CAP desde datos en memoria.

    Soporta:
    - XML plano (UTF-8 o ISO-8859-15 / Latin-1)
    - Archivos GZIP (.gz)
    - Archivos TAR (.tar, .tar.gz, .tgz) y TARs anidados dentro de GZ
    """
    if not data or depth > 5:
        return []

    stripped = data.lstrip()
    if stripped.startswith(b'<?xml') or stripped.startswith(b'<alert'):
        for enc in ('utf-8', 'iso-8859-15', 'latin-1'):
            try:
                return [data.decode(enc).strip()]
            except Exception:
                continue
        return [data.decode('utf-8', errors='replace').strip()]

    # Si es gzip (magic 0x1f 0x8b)
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        try:
            import gzip as _gzip
            decompressed = _gzip.decompress(data)
            return extract_xmls_from_bytes(decompressed, depth=depth + 1)
        except Exception:
            pass

    # Si es tar (comprimido o sin comprimir)
    try:
        import io as _io
        import tarfile as _tarfile
        bio = _io.BytesIO(data)
        results: list[str] = []
        with _tarfile.open(fileobj=bio, mode='r:*') as tar:
            for m in tar.getmembers():
                if not m.isfile():
                    continue
                f = tar.extractfile(m)
                if not f:
                    continue
                try:
                    m_bytes = f.read()
                    results.extend(extract_xmls_from_bytes(m_bytes, depth=depth + 1))
                except Exception:
                    continue
                finally:
                    try:
                        f.close()
                    except Exception:
                        pass
        return results
    except Exception:
        pass

    return []


def _filter_alert_xml_for_province(xml_text: str, emma_info: Optional[dict], prov_raw: str) -> bool:
    """Comprueba si un documento XML CAP corresponde a la provincia configurada."""
    if not xml_text:
        return False
    if not emma_info and not prov_raw:
        return True

    # 1. Búsqueda por geocodes EMMA_ID y área en la estructura XML
    try:
        import xml.etree.ElementTree as ET
        ns = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
        root = ET.fromstring(xml_text)
        for info in root.findall('cap:info', ns):
            area_el = info.find('cap:area', ns)
            if area_el is not None:
                # Comprobar código de zona EMMA (ej. '6111' para Cádiz o '61' para CCAA completa)
                if emma_info and emma_info.get('emma_prefix'):
                    prefix = str(emma_info['emma_prefix'])
                    for gc in area_el.findall('cap:geocode', ns):
                        v = (gc.findtext('cap:value', default='', namespaces=ns) or '').strip()
                        if v.startswith(prefix):
                            return True

                # Comprobar descripción de área
                area_desc = (area_el.findtext('cap:areaDesc', default='', namespaces=ns) or '').upper()
                accents_map = str.maketrans("ÁÉÍÓÚÀÈÌÒÙÄËÏÖÜÂÊÎÔÛ", "AEIOUAEIOUAEIOUAEIOU")
                area_desc_norm = area_desc.translate(accents_map)

                targets = []
                if emma_info:
                    targets.extend(emma_info.get('aliases', []))
                    if emma_info.get('name'):
                        targets.append(emma_info['name'])
                if prov_raw:
                    targets.append(prov_raw)

                for t in targets:
                    t_norm = (t or '').upper().translate(accents_map)
                    if t_norm and t_norm in area_desc_norm:
                        return True
    except Exception:
        pass

    # 2. Fallback textual rápido sobre el XML completo normalizado
    accents_map = str.maketrans("ÁÉÍÓÚÀÈÌÒÙÄËÏÖÜÂÊÎÔÛ", "AEIOUAEIOUAEIOUAEIOU")
    xml_norm = xml_text.upper().translate(accents_map)

    if emma_info:
        if emma_info.get('emma_prefix') and emma_info['emma_prefix'] in xml_norm:
            return True
        for a in emma_info.get('aliases', []):
            a_norm = a.upper().translate(accents_map)
            if a_norm and a_norm in xml_norm:
                return True

    if prov_raw:
        p_norm = prov_raw.upper().translate(accents_map)
        if p_norm and p_norm in xml_norm:
            return True

    return False


def fetch_aemet_alerts_for_province(aemet: Aemet) -> Optional[list[str]]:
    """Obtiene las alertas meteorológicas activas desde el endpoint de área C.A. de AEMET.

    Endpoints:
    1) GET https://opendata.aemet.es/opendata/api/avisos_cap/ultimoelaborado/area/{ccaa_code}
       (p. ej. 61 para Andalucía / Cádiz).
    2) Fallback: .../avisos_cap/ultimoelaborado/area/esp (nacional).

    Devuelve:
      - list[str] con los XMLs filtrados para la provincia (vacía [] si no hay alertas activas).
      - None si hubo un error HTTP/red y se debe intentar el archivo histórico.
    """
    import requests
    from urllib.parse import quote

    api_key = getattr(aemet, 'api_key', None)
    if not api_key:
        return []

    emma_info = aemet.get_emma_info()
    ccaa_code = (emma_info.get('ccaa_code') if emma_info else None) or aemet.ccaa_code()
    prov_raw = (aemet.province or '').strip()

    log_p(f"[cron] fetch_aemet: buscando alertas para provincia='{prov_raw}' (CCAA={ccaa_code})")

    base_filter = 'https://opendata.aemet.es/opendata/api/avisos_cap/ultimoelaborado/area'
    urls_to_try: list[str] = []
    if ccaa_code:
        urls_to_try.append(f"{base_filter}/{quote(str(ccaa_code))}")
    urls_to_try.append(f"{base_filter}/esp")

    req_headers = {'Accept': 'application/json', 'api_key': api_key}
    params = {'api_key': api_key}

    success_attempt = False
    for url in urls_to_try:
        try:
            log_p(f"[cron] fetch_aemet: GET {url}")
            r1 = requests.get(url, headers=req_headers, params=params, timeout=10)
            if r1.status_code != 200:
                log_p(f"[cron] fetch_aemet: status={r1.status_code} en {url}", level="WARN")
                continue

            j = r1.json()
            if not isinstance(j, dict):
                continue
            estado = j.get('estado')
            if estado is not None and int(str(estado)) != 200:
                log_p(f"[cron] fetch_aemet: estado={estado} desc={j.get('descripcion')}", level="WARN")
                continue

            datos_url = j.get('datos')
            if not datos_url:
                continue

            log_p(f"[cron] fetch_aemet: GET datos {datos_url}")
            r2 = requests.get(datos_url, timeout=20)
            if r2.status_code != 200:
                log_p(f"[cron] fetch_aemet: datos status={r2.status_code}", level="WARN")
                continue

            success_attempt = True
            all_xmls = extract_xmls_from_bytes(r2.content)
            log_p(f"[cron] fetch_aemet: extraídos {len(all_xmls)} XMLs desde {url}")

            filtered_xmls = [
                xml_str for xml_str in all_xmls
                if _filter_alert_xml_for_province(xml_str, emma_info, prov_raw)
            ]
            log_p(f"[cron] fetch_aemet: filtrados {len(filtered_xmls)}/{len(all_xmls)} XMLs para '{prov_raw}'")
            return filtered_xmls

        except Exception as e:
            log_p(f"[cron] fetch_aemet: excepción con {url}: {e}", level="WARN")
            continue

    return None if not success_attempt else []


def fetch_aemet_alerts_archive(aemet: Aemet) -> Optional[list[str]]:
    """Obtiene alertas CAP desde el endpoint de ARCHIVO por rango temporal (tar.gz) y filtra por provincia.

    Devuelve:
      - None si hubo un error HTTP/red/parsing (la descarga falló).
      - [] si la descarga fue correcta pero no hay avisos para la provincia.
      - [...] lista de XMLs que afectan a la provincia.
    """
    import requests
    from urllib.parse import quote
    from datetime import datetime, timedelta, timezone

    api_key = getattr(aemet, 'api_key', None)
    if not api_key:
        return []

    emma_info = aemet.get_emma_info()
    prov_raw = (aemet.province or '').strip()

    # Rango temporal: desde hoy 00:00 UTC hasta mañana 00:00 UTC (máx 2 días permitido por AEMET)
    now_utc = datetime.now(timezone.utc)
    start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=2)

    def fmt(dt: datetime) -> str:
        return quote(dt.strftime('%Y-%m-%dT%H:%M:%S') + 'UTC', safe='')

    base = 'https://opendata.aemet.es/opendata/api/avisos_cap/archivo'
    url = f"{base}/fechaini/{fmt(start)}/fechafin/{fmt(end)}"

    params = {'api_key': api_key}
    req_headers = {'Accept': 'application/json', 'api_key': api_key}

    try:
        log_p(f"[cron] fetch_aemet-archivo: GET {url}")
        r1 = requests.get(url, headers=req_headers, params=params, timeout=10)
        if r1.status_code != 200:
            log_p(f"[cron] fetch_aemet-archivo: status={r1.status_code}", level="WARN")
            return None

        j = r1.json()
        if not isinstance(j, dict):
            return None
        estado = j.get('estado')
        if estado is None or int(str(estado)) != 200:
            if int(str(estado or 0)) == 404:
                log_p("[cron] fetch_aemet-archivo: estado=404 (sin avisos para el rango)")
                return []
            log_p(f"[cron] fetch_aemet-archivo: estado={estado} desc={j.get('descripcion')}", level="WARN")
            return None

        datos_url = j.get('datos')
        if not datos_url:
            return None

        log_p(f"[cron] fetch_aemet-archivo: GET datos {datos_url}")
        r2 = requests.get(datos_url, timeout=30)
        if r2.status_code != 200:
            return None

        all_xmls = extract_xmls_from_bytes(r2.content)
        log_p(f"[cron] fetch_aemet-archivo: extraídos {len(all_xmls)} XMLs totales")

        filtered_xmls = [
            xml_str for xml_str in all_xmls
            if _filter_alert_xml_for_province(xml_str, emma_info, prov_raw)
        ]
        log_p(f"[cron] fetch_aemet-archivo: filtrados {len(filtered_xmls)}/{len(all_xmls)} XMLs para '{prov_raw}'")
        return filtered_xmls

    except Exception as e:
        log_p(f"[cron] fetch_aemet-archivo: error: {e}", level="WARN")
        return None


def weather_forecast_aemet() -> None:
    """Descarga la predicción multi-día del municipio y la guarda como histórico.

    - Cadencia: según AEMET_PERIOD (mismo helper que el resto de AEMET).
    - Solo si hay AEMET_API_KEY configurada.
    - Guarda en `aemet_weather` con scope='forecast' para que /prevision lo
      sirva offline (BD-first) con fallback on-demand en el propio comando.
    """
    db = Database()
    task_name = 'aemet_forecast_fetch'

    aemet = Aemet()
    period_min = aemet.period_to_minutes(aemet.period)

    if not _should_run(db, task_name, period_min):
        log_p(f"[cron] weather_forecast_aemet: omitido (cooldown {period_min}min)")
        return

    if not getattr(env, 'AEMET_API_KEY', None):
        log_p("[cron] weather_forecast_aemet: AEMET_API_KEY vacío; no se consulta API")
        db.set_task_run(task_name)
        return

    try:
        days = int(getattr(env, 'AEMET_FORECAST_DAYS', 4) or 4)
        text = aemet.fetch_city_forecast_multi(days=days)
        if text:
            new_id = db.aemet_weather_insert(
                scope='forecast',
                content=text,
                province=aemet.province,
                province_code=aemet.province_code(),
                city=aemet.city,
                city_code=aemet.resolve_city_code(),
                day='multi',
                data_raw=text,
            )
            log_p(f"[cron] weather_forecast_aemet: previsión guardada id={new_id} len={len(text)}")
        else:
            log_p("[cron] weather_forecast_aemet: sin datos de previsión municipal")
    except Exception as e:
        log_p(f"[cron] weather_forecast_aemet: excepción general: {e}", level="WARN")
    finally:
        db.set_task_run(task_name)


def tides_fetch() -> None:
    """Descarga la predicción de mareas y la guarda en BD (servida por /marea).

    - Cadencia: TIDES_PERIOD_MIN (por defecto 360 min = 6 h).
    - Fuente: WorldTides (si TIDES_API_KEY) u Open-Meteo Marine (gratis).
    - Solo guarda datos de fuente real; si únicamente sale la estimación
      astronómica, no se persiste (el comando ya la calcula on-demand offline).
    """
    db = Database()
    task_name = 'tides_fetch'

    period_min = int(getattr(env, 'TIDES_PERIOD_MIN', 360) or 360)
    if not _should_run(db, task_name, period_min):
        log_p(f"[cron] tides_fetch: omitido (cooldown {period_min}min)")
        return

    try:
        from Models.Tides import compute_tides
        days = int(getattr(env, 'TIDES_DAYS', 2) or 2)
        result = compute_tides(days=days, allow_network=True)
        if result and result.get('extremes') and not result.get('approximate'):
            new_id = db.tides_insert(
                location=result.get('name'),
                source=result.get('source'),
                approximate=False,
                extremes=result.get('extremes'),
            )
            log_p(f"[cron] tides_fetch: guardado id={new_id} fuente={result.get('source')} "
                  f"extremos={len(result.get('extremes'))}")
        else:
            log_p("[cron] tides_fetch: sin datos de fuente real (no se persiste estimación)")
    except Exception as e:
        log_p(f"[cron] tides_fetch: excepción general: {e}", level="WARN")
    finally:
        db.set_task_run(task_name)


def run_all():
    """Ejecuta todas las tareas con sus restricciones.

    Pensado para llamarse desde cron cada minuto.
    """
    log_p("[cron] run_all: inicio")
    chiste_upload()
    chiste_download()
    send_trace()
    check_aemet()
    weather_aemet()
    weather_forecast_aemet()
    tides_fetch()
    encuestas_expire()
    log_p("[cron] run_all: fin")


def encuestas_expire() -> None:
    """Cierra en BD las encuestas vencidas (barrido perezoso movido al cron).

    Las lecturas de /encuesta NO escriben (calculan el estado efectivo en
    memoria); aquí se materializa el cierre real, como mucho una vez por minuto.
    """
    try:
        n = Database().encuesta_expire_due()
        if n:
            log_p(f"[cron] encuestas_expire: cerradas {n} encuesta(s) vencida(s)")
    except Exception as e:
        log_p(f"[cron] encuestas_expire: error: {e}", level="WARN")


if __name__ == '__main__':
    run_all()