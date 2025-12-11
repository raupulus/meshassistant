from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import Optional

from Models.Database import Database
from Models.Api import Api
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
        return

    api = Api()
    # Configurar API key específica para este endpoint si está definida
    api_key = getattr(env, 'CHISTES_API_KEY', None)
    if api_key:
        api.set_apikey(api_key)
    url = getattr(env, 'CHISTES_URL_UPLOAD', None)
    if not url:
        return

    to_send = db.get_chistes_to_upload(limit=200)
    if not to_send:
        db.set_task_run(task_name)
        return

    uploaded_ids = []
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
                continue
            uploaded_ids.append(item['id'])
        except Exception:
            # continuar con el siguiente
            continue

    if uploaded_ids:
        db.mark_chistes_uploaded(uploaded_ids)
    db.set_task_run(task_name)


def chiste_download() -> None:
    """Descarga chistes nuevos desde la API. Frecuencia: máxima 1/hora."""
    db = Database()
    task_name = 'chiste_download'
    if not _should_run(db, task_name, 60):
        return

    api = Api()
    # Configurar API key específica para este endpoint si está definida
    api_key = getattr(env, 'CHISTES_API_KEY', None)
    if api_key:
        api.set_apikey(api_key)
    url = getattr(env, 'CHISTES_URL_DOWNLOAD', None)
    if not url:
        return

    last_id = db.get_last_downloaded_chiste_id()
    payload = {'last_id': last_id}
    try:
        data = api.download(url, payload)
        if isinstance(data, dict) and 'items' in data:
            items = data['items']
        elif isinstance(data, list):
            items = data
        else:
            items = []
        db.bulk_insert_api_chistes(items)
    except Exception:
        # ignorar errores de red momentáneos
        pass
    finally:
        db.set_task_run(task_name)


def send_trace() -> None:
    """Encola la ejecución de un traceroute para que lo procese el proceso principal.

    Restricciones:
    - Throttle global: 1 intento cada 5 minutos medido con traces.updated_at del último procesado
    - Cada nodo como máximo 1 vez por semana (selección de candidato)
    """
    db = Database()

    # Throttle global 5 minutos basado en el último trace realizado (updated_at)
    last_done_iso = db.get_last_trace_updated_at()
    if last_done_iso:
        try:
            last_dt = datetime.fromisoformat(last_done_iso)
            if datetime.now() - last_dt < timedelta(minutes=5):
                return
        except Exception:
            pass

    # Seleccionar próximo nodo candidato (>= 7 días desde último trace) y sin pendientes
    node_id = db.get_next_node_to_trace(min_days=7)
    if node_id:
        # Encolar petición en la propia tabla traces (status='pending')
        db.enqueue_trace(node_id)


def check_aemet() -> None:
    """Comprueba alertas de AEMET y limita envíos.

    - Ejecutar cada 10 minutos como máximo
    - Enviar solo 1 mensaje al día (canal 6)
    """
    db = Database()
    if not _should_run(db, 'check_aemet', 10):
        return

    # Comprobación de límite diario
    last_daily = _parse_dt(db.get_task_last_run('aemet_sent'))
    already_sent_today = last_daily and last_daily.date() == date.today()

    # TODO: Implementar consulta real a AEMET
    has_alert = False  # Placeholder: cambiar cuando se conecte a la API de AEMET

    if has_alert and not already_sent_today:
        # TODO: Enviar por el canal 6 (data.channels). Aquí se podría insertar en la tabla queue.
        # from data import channels
        # channel_name = channels[6]['name']
        # enqueue message or call interface if disponible
        db.set_task_run('aemet_sent')

    # Registrar ejecución de chequeo, aunque no envíe
    db.set_task_run('check_aemet')


def run_all():
    """Ejecuta todas las tareas con sus restricciones.

    Pensado para llamarse desde cron cada minuto.
    """
    chiste_upload()
    chiste_download()
    send_trace()
    check_aemet()


if __name__ == '__main__':
    run_all()