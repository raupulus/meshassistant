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

    Restricciones y cadencias:
    - Routers: 40 segundos entre trazas matinales (a partir de las 06:00 AM).
    - Clientes diurnos (08:00 - 23:00): 1 trace por hora (60 minutos).
    - Clientes nocturnos (23:00 - 08:00): 1 trace cada 5 minutos.
    - Los traces manuales desde la web se encolan directamente y se ejecutan de inmediato en main.py.
    """
    # Permitir deshabilitar traces por configuración
    if not getattr(env, 'ENABLE_TRACES', False):
        log_p("[cron] send_trace: deshabilitado por ENABLE_TRACES=False")
        return

    db = Database()

    # Limpiar trazas pendientes obsoletas que se hayan quedado colgadas (>15 min)
    cleaned = db.cleanup_stale_pending_traces(max_age_minutes=15)
    if cleaned > 0:
        log_p(f"[cron] send_trace: expiradas {cleaned} trazas pendientes obsoletas")

    # Si ya hay una traza pendiente en cola siendo procesada por main.py (ej. lanzada desde la web), no encolar otra
    pending = db.get_next_pending_trace()
    if pending:
        log_p(f"[cron] send_trace: omitido (ya hay un trace pendiente en proceso: id={pending['id']})")
        return

    # Parámetros de selección de candidatos
    hops_limit = int(getattr(env, 'TRACES_HOPS', 2) or 2)
    reload_hours = int(getattr(env, 'TRACES_RELOAD_INTERVAL', 120) or 120)
    router_reload_hours = int(getattr(env, 'ROUTER_TRACE_INTERVAL_HOURS', 24) or 24)
    router_max_hops = int(getattr(env, 'ROUTER_MAX_HOPS', 2) or 2)
    router_retry_short_hours = int(getattr(env, 'ROUTER_RETRY_SHORT_HOURS', 1) or 1)
    router_max_retries = int(getattr(env, 'ROUTER_MAX_RETRIES', 5) or 5)
    router_retry_long_hours = int(getattr(env, 'ROUTER_RETRY_LONG_HOURS', 24) or 24)
    router_start_hour = int(getattr(env, 'ROUTER_TRACE_START_HOUR', 6) or 6)
    max_inactive_days = int(getattr(env, 'TRACES_MAX_INACTIVE_DAYS', 7) or 7)
    retry_hours = int(getattr(env, 'TRACES_RETRY_INTERVAL', 24) or 24)

    routers_cfg = getattr(env, 'ROUTER_NODES', None) or getattr(env, 'ROUTERS_LIST', None) or []
    if isinstance(routers_cfg, str):
        routers_cfg = [r.strip() for r in routers_cfg.split(',') if r.strip()]

    node_id = db.get_next_node_to_trace(
        hops_limit=hops_limit,
        reload_hours=reload_hours,
        router_reload_hours=router_reload_hours,
        router_max_hops=router_max_hops,
        router_retry_short_hours=router_retry_short_hours,
        router_max_retries=router_max_retries,
        router_retry_long_hours=router_retry_long_hours,
        retry_hours=retry_hours,
        max_inactive_days=max_inactive_days,
        router_start_hour=router_start_hour,
        router_identifiers=routers_cfg,
    )
    if not node_id:
        log_p(f"[cron] send_trace: ningún nodo candidato (≤{hops_limit} hops, activos en {max_inactive_days}d, no MQTT, ventanas cumplidas)")
        return

    # Throttle dinámico según tipo de nodo y franja horaria
    is_router = db.is_router_node(node_id, routers_cfg)
    last_done_iso = db.get_last_trace_updated_at()
    now = datetime.now()

    if last_done_iso:
        try:
            last_dt = datetime.fromisoformat(last_done_iso)
            elapsed = (now - last_dt).total_seconds()

            if is_router:
                router_sec = int(getattr(env, 'ROUTER_TRACE_INTERVAL_SECONDS', 40) or 40)
                if elapsed < router_sec:
                    log_p(f"[cron] send_trace: omitido (cooldown router {router_sec}s, faltan {int(router_sec - elapsed)}s)")
                    return
            else:
                peak_start = int(getattr(env, 'TRACES_PEAK_START_HOUR', 8) or 8)
                peak_end = int(getattr(env, 'TRACES_PEAK_END_HOUR', 23) or 23)
                is_peak = (peak_start <= now.hour < peak_end)

                if is_peak:
                    interval_min = int(getattr(env, 'TRACES_INTERVAL_PEAK', 60) or 60)
                    if elapsed < interval_min * 60:
                        rem_min = int((interval_min * 60 - elapsed) / 60)
                        log_p(f"[cron] send_trace: omitido (cooldown diurno {interval_min}min [1/h], faltan ~{rem_min}m)")
                        return
                else:
                    interval_min = int(getattr(env, 'TRACES_INTERVAL_OFFPEAK', 5) or 5)
                    if elapsed < interval_min * 60:
                        rem_min = int((interval_min * 60 - elapsed) / 60)
                        log_p(f"[cron] send_trace: omitido (cooldown nocturno {interval_min}min, faltan ~{rem_min}m)")
                        return
        except Exception:
            pass

    # Encolar petición en la propia tabla traces (status='pending')
    trace_id = db.enqueue_trace(node_id)
    node_type_str = "router" if is_router else "cliente"
    log_p(f"[cron] send_trace: encolado trace #{trace_id} para {node_type_str} {node_id}")


def request_router_telemetry() -> None:
    """Solicita una vez al día a partir de las 07:00 AM la telemetría de batería a routers cercanos."""
    db = Database()
    task_name = 'router_telemetry_request'

    # Cooldown de 24 horas (1440 minutos)
    if not _should_run(db, task_name, 1440):
        return

    start_hour = int(getattr(env, 'ROUTER_TELEMETRY_START_HOUR', 7) or 7)
    if datetime.now().hour < start_hour:
        return

    routers_cfg = getattr(env, 'ROUTER_NODES', None) or getattr(env, 'ROUTERS_LIST', None) or []
    if isinstance(routers_cfg, str):
        routers_cfg = [r.strip() for r in routers_cfg.split(',') if r.strip()]

    # Obtener routers cercanos (<= 2 saltos exteriores)
    router_nodes = db.get_router_nodes(configured_identifiers=routers_cfg, max_hops=2)
    enqueued = 0
    for r in router_nodes:
        nid = r.get('node_id')
        if not nid or (not str(nid).startswith('!') and not str(nid).isdigit()):
            ident = r.get('identifier') or r.get('short_name') or nid
            if ident:
                found = db.get_node_by_identifier(str(ident))
                if found and found.get('node_id') and str(found['node_id']).startswith('!'):
                    nid = found['node_id']

        if not nid or not str(nid).startswith('!') or nid in ('RAU0', '!63ca1feb'):
            continue
        # Encolar en outbox para que main.py lo despache espaciadamente
        db.enqueue_outbox(
            text="__REQ_TELEMETRY__",
            dest=nid,
            channel=0,
        )
        enqueued += 1

    if enqueued > 0:
        log_p(f"[cron] request_router_telemetry: encoladas {enqueued} solicitudes de telemetría para routers cercanos")
    db.set_task_run(task_name)


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


def check_aemet_key_expiry() -> None:
    """Comprueba la caducidad del JWT de AEMET_API_KEY y emite aviso si expira pronto."""
    db = Database()
    task_name = 'aemet_key_expiry_check'
    if not _should_run(db, task_name, 1440):
        return

    api_key = getattr(env, 'AEMET_API_KEY', None)
    if not api_key:
        db.set_task_run(task_name)
        return

    try:
        aemet = Aemet()
        is_expired, days_left, exp_date = aemet.check_api_key_expiry(api_key)
        if days_left is None:
            db.set_task_run(task_name)
            return

        warn_days = int(getattr(env, 'AEMET_EXPIRY_WARNING_DAYS', 10) or 10)
        if days_left <= warn_days or is_expired:
            today_tag = f"aemet_key_warn_{datetime.now().strftime('%Y%m%d')}"
            if not db.get_task_last_run(today_tag):
                channels = getattr(env, 'AEMET_EXPIRY_WARNING_CHANNELS', None)
                if channels is None:
                    channels = [6]  # Canal raupulus por defecto

                if is_expired:
                    msg_text = f"🚨 [AEMET] Tu API Key HA CADUCADO (el {exp_date}). Renuévala en opendata.aemet.es."
                else:
                    msg_text = f"⚠️ [AEMET] Tu API Key caduca en {days_left} días ({exp_date}). Renuévala en opendata.aemet.es."

                for ch in channels:
                    ch_idx = ch if isinstance(ch, int) else (6 if str(ch).lower() == 'raupulus' else 0)
                    db.outbox_enqueue(msg_text, dest="^all", channel=ch_idx)
                    log_p(f"[cron] check_aemet_key_expiry: aviso encolado en canal {ch_idx}: {msg_text}")

                db.set_task_run(today_tag)
    except Exception as e:
        log_p(f"[cron] check_aemet_key_expiry: error: {e}", level="WARN")
    finally:
        db.set_task_run(task_name)


def maritime_aemet() -> None:
    """Descarga el boletín marítimo costero a las 12:05 y 20:05 con 3 reintentos cada 10 min."""
    db = Database()
    if not getattr(env, 'AEMET_API_KEY', None):
        return

    now = datetime.now()
    hour = now.hour
    minute = now.minute

    # Ventanas de emisión oficial: 12:05 y 20:05 (+ reintentos en :15, :25, :35)
    slot_id = None
    if hour == 12 and 5 <= minute <= 40:
        slot_id = f"{now.strftime('%Y%m%d')}_12"
    elif hour == 20 and 5 <= minute <= 40:
        slot_id = f"{now.strftime('%Y%m%d')}_20"

    if not slot_id:
        return

    success_tag = f"maritime_success_{slot_id}"
    if db.get_task_last_run(success_tag):
        return

    last_attempt_tag = f"maritime_attempt_{slot_id}"
    last_attempt = db.get_task_last_run(last_attempt_tag)
    if last_attempt:
        try:
            if datetime.now() - datetime.fromisoformat(last_attempt) < timedelta(minutes=10):
                return
        except Exception:
            pass

    db.set_task_run(last_attempt_tag)
    log_p(f"[cron] maritime_aemet: intentando descarga slot {slot_id} (minuto {minute})")

    try:
        aemet = Aemet()
        costa_code = getattr(env, 'AEMET_MARITIME_COAST_CODE', '42') or '42'
        data = aemet.fetch_maritime_coastal(costa_code=costa_code)
        if data:
            summary = aemet.format_maritime_coastal(data)
            if summary:
                new_id = db.aemet_maritime_insert(
                    costa_code=costa_code,
                    costa_name="Costa Andalucía Occidental / Cádiz",
                    data_json=data,
                    summary=summary,
                )
                log_p(f"[cron] maritime_aemet: guardado exitoso id={new_id} len={len(summary)}")
                db.set_task_run(success_tag)
    except Exception as e:
        log_p(f"[cron] maritime_aemet: error en intento: {e}", level="WARN")


def observation_aemet() -> None:
    """Descarga periódicamente la observación de la estación meteorológica física."""
    db = Database()
    task_name = 'aemet_observation_fetch'
    if not _should_run(db, task_name, 60):
        return

    if not getattr(env, 'AEMET_API_KEY', None):
        db.set_task_run(task_name)
        return

    try:
        aemet = Aemet()
        station_id = getattr(env, 'AEMET_OBSERVATION_STATION', '5972X') or '5972X'
        obs_data = aemet.fetch_station_observation(station_id=station_id)
        if obs_data:
            summary = aemet.format_station_observation(obs_data)
            if summary:
                new_id = db.aemet_observation_insert(
                    station_id=station_id,
                    station_name="Cádiz/Costa",
                    data_json=obs_data,
                    summary=summary,
                )
                log_p(f"[cron] observation_aemet: guardado exitoso id={new_id} len={len(summary)}")
    except Exception as e:
        log_p(f"[cron] observation_aemet: error: {e}", level="WARN")
    finally:
        db.set_task_run(task_name)


def weather_forecast_aemet() -> None:
    """Descarga predicción municipal (diaria 7 días y horaria) y provincial (mañana)."""
    db = Database()
    task_name = 'aemet_forecast_fetch'
    period_min = 180  # cada 3 horas

    if not _should_run(db, task_name, period_min):
        return

    if not getattr(env, 'AEMET_API_KEY', None):
        db.set_task_run(task_name)
        return

    try:
        aemet = Aemet()
        city_code = aemet.resolve_city_code() or '11016'
        city_name = aemet.city or 'Chipiona'
        province = aemet.province or 'Cádiz'

        # 1) Predicción diaria 7 días
        data_d = aemet.fetch_daily_forecast(city_code=city_code)
        if data_d:
            sum_3d = aemet.format_daily_forecast(data_d, days=3)
            sum_7d = aemet.format_daily_forecast(data_d, days=7)
            db.aemet_forecast_daily_insert(
                city_code=city_code,
                city_name=city_name,
                province=province,
                data_json=data_d,
                summary_3d=sum_3d,
                summary_7d=sum_7d,
            )
            log_p(f"[cron] weather_forecast_aemet: predicción diaria 7d guardada ({city_name})")

        # 2) Predicción horaria
        data_h = aemet.fetch_hourly_forecast(city_code=city_code)
        if data_h:
            sum_24h = aemet.format_hourly_forecast(data_h, hours=12)
            db.aemet_forecast_hourly_insert(
                city_code=city_code,
                city_name=city_name,
                province=province,
                data_json=data_h,
                summary_24h=sum_24h,
            )
            log_p(f"[cron] weather_forecast_aemet: predicción horaria guardada ({city_name})")

        # 3) Texto provincial para mañana
        txt_manana = aemet.fetch_province_forecast(day='manana')
        if txt_manana:
            db.aemet_weather_insert(
                scope='province',
                content=txt_manana,
                province=province,
                province_code=aemet.province_code(),
                day='manana',
                data_raw=txt_manana,
            )
            log_p("[cron] weather_forecast_aemet: texto provincial de mañana guardado")
    except Exception as e:
        log_p(f"[cron] weather_forecast_aemet: excepción: {e}", level="WARN")
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
    request_router_telemetry()
    check_aemet_key_expiry()
    check_aemet()
    weather_aemet()
    weather_forecast_aemet()
    maritime_aemet()
    observation_aemet()
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