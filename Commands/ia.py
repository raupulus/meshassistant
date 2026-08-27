from __future__ import annotations

import queue
import threading
import time
import requests
from functions import log_p
import env

# Cola FIFO en memoria para peticiones a la API de IA (1 sola inferencia a la vez)
_MAX_QUEUE_SIZE = int(getattr(env, 'IA_MAX_QUEUE', 10) or 10)
_ia_queue: queue.Queue = queue.Queue(maxsize=_MAX_QUEUE_SIZE)
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()


def _ensure_worker_running():
    """Garantiza que el hilo worker despachador esté en ejecución."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(
                target=_ia_worker_loop,
                daemon=True,
                name="ia_worker_thread",
            )
            _worker_thread.start()


def _ia_worker_loop():
    """Bucle consumidor que procesa peticiones secuencialmente hacia la API."""
    log_p("[IA Worker] Hilo despachador de IA iniciado", level="INFO")
    while True:
        try:
            task = _ia_queue.get()
            try:
                _execute_ia_task(task)
            except Exception as e:
                log_p(f"[IA Worker] Error procesando tarea de IA: {e}", level="WARN")
            finally:
                _ia_queue.task_done()
        except Exception as e:
            log_p(f"[IA Worker] Error fatal en loop: {e}", level="ERROR")
            time.sleep(1)


def _execute_ia_task(task: dict):
    """Ejecuta una petición HTTP a la API y transmite las respuestas por Meshtastic."""
    interface = task["interface"]
    metadata = task["metadata"]
    tipo = task.get("tipo", "consulta")
    from_id = task.get("from_id", "desconocido")

    api_url = getattr(env, 'IA_API_URL', 'http://172.18.1.121:8870').rstrip('/')
    api_token = getattr(env, 'IA_API_TOKEN', '')
    timeout = int(getattr(env, 'IA_TIMEOUT', 120) or 120)

    headers = {
        "Content-Type": "application/json",
    }
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    err_msg = "Servidor IA de @raupulus no disponible en este momento."

    # 1. Caso Reseteo de Conversación
    if tipo == "reset":
        try:
            url = f"{api_url}/v1/conversacion/reset"
            payload = {"id_conversacion": f"meshtastic:{from_id}"}
            log_p(f"[IA] Solicitando reset para {from_id} en {url}")
            res = requests.post(url, json=payload, headers=headers, timeout=15)
            if res.status_code == 200 and res.json().get("ok"):
                interface.reply_to_message("✅ Conversación de IA reiniciada.", metadata)
            else:
                log_p(f"[IA] Reset falló con status {res.status_code}: {res.text}", level="WARN")
                interface.reply_to_message(err_msg, metadata)
        except Exception as e:
            log_p(f"[IA] Excepción conectando a API para reset: {e}", level="WARN")
            interface.reply_to_message(err_msg, metadata)
        return

    # 2. Caso Consulta RAG de Emergencia
    consulta = task.get("consulta", "")

    payload = {
        "consulta": consulta,
        "id_conversacion": f"meshtastic:{from_id}",
        "cliente": f"meshtastic:{from_id}",
        "reset_conversacion": False,
    }

    lat = getattr(env, 'LOCATION_LAT', None)
    lon = getattr(env, 'LOCATION_LON', None)
    if lat is not None and lon is not None:
        try:
            payload["ubicacion"] = {"lat": float(lat), "lon": float(lon)}
        except (ValueError, TypeError):
            pass

    try:
        url = f"{api_url}/v1/consulta"
        log_p(f"[IA] Enviando consulta de {from_id} ({len(consulta)} chars) a {url}")
        res = requests.post(url, json=payload, headers=headers, timeout=timeout)

        if res.status_code == 200:
            data = res.json()
            if data.get("ok") and data.get("mensajes"):
                mensajes = data.get("mensajes", [])
                tiempo_ms = data.get("tiempo_ms", 0)
                modelo = data.get("modelo", "")
                log_p(f"[IA] Respuesta recibida ({tiempo_ms}ms, modelo: {modelo}, {len(mensajes)} partes)")

                # Transmisión secuencial respetando el contrato LoRa (<= MESH_MAX_BYTES)
                from functions import split_messages, MESH_MAX_BYTES

                partes_finales: list[str] = []
                for msg_raw in mensajes:
                    subpartes = split_messages(msg_raw, max_bytes=MESH_MAX_BYTES)
                    partes_finales.extend(subpartes)

                # Máximo 3 partes por respuesta
                partes_finales = partes_finales[:3]

                for i, parte in enumerate(partes_finales):
                    if i > 0:
                        # Pausa defensiva de 3.0s entre mensajes para no saturar la malla
                        time.sleep(3.0)
                    interface.reply_to_message(parte, metadata)
                return
            else:
                log_p(f"[IA] Respuesta no ok de la API: {data}", level="WARN")
                interface.reply_to_message(err_msg, metadata)
                return
        else:
            log_p(f"[IA] Error HTTP {res.status_code} de la API: {res.text}", level="WARN")
            interface.reply_to_message(err_msg, metadata)
            return

    except Exception as e:
        log_p(f"[IA] Excepción consultando API de IA: {e}", level="WARN")
        interface.reply_to_message(err_msg, metadata)


def ia_callback(interface, args, msg, metadata):
    """Callback invocado al recibir /ia o !ia."""
    log_p("Comando /ia recibido")

    metadata = metadata or {}
    node_from = metadata.get('node_from') if isinstance(metadata.get('node_from'), dict) else {}
    from_id = node_from.get('id') or (metadata.get('node_from') if isinstance(metadata.get('node_from'), str) else None) or 'desconocido'

    # 0. Filtro de canal: /ia solo responde en privado y en los canales configurados en IA_CHANNELS
    is_direct = metadata.get('is_direct', False)
    channel_idx = metadata.get('channel', 0)

    if not is_direct:
        from data import channels
        channel_info = channels.get(channel_idx, {})
        channel_name = (channel_info.get('name') or '').lower()

        default_channels = ['cadiz', 'chipiona', 'bots', 'raupulus', 'frikidevs', 2, 3, 4, 6, 7]
        allowed_channels = getattr(env, 'IA_CHANNELS', default_channels)
        allowed = []
        for ch in (allowed_channels or []):
            if isinstance(ch, int):
                allowed.append(ch)
            elif isinstance(ch, str):
                allowed.append(ch.lower())

        is_allowed = (channel_idx in allowed) or (channel_name in allowed)
        if not is_allowed:
            log_p(
                f"[IA] Comando ignorado en canal {channel_idx} ('{channel_name}'): "
                f"solo permitido en privado y canales autorizados ({allowed_channels})",
                level="INFO"
            )
            return

    # 1. Ayuda o información del comando (respuesta inmediata)
    if not args or (len(args) == 1 and args[0].lower() in ['help', 'ayuda', 'info']):
        ayuda = "Asistente IA: Usa !ia <pregunta>. Para resetear memoria usa !ia reset o !ia nueva. Canales: Cadiz, Chipiona, bots, raupulus, Frikidevs y privado."
        interface.reply_to_message(ayuda, metadata)
        return

    # Verificar si el servicio está habilitado
    if not getattr(env, 'IA_API_ENABLED', False):
        interface.reply_to_message("⚠️ El servicio de IA no está habilitado.", metadata)
        return

    # 2. Reseteo de contexto
    if args[0].lower() in ['reset', 'nueva', 'clear']:
        try:
            _ia_queue.put_nowait({
                "tipo": "reset",
                "interface": interface,
                "metadata": metadata,
                "from_id": from_id,
            })
            _ensure_worker_running()
        except queue.Full:
            interface.reply_to_message("⚠️ Cola de peticiones de IA ocupada, inténtalo en un minuto.", metadata)
        return

    # 3. Consulta normal
    query_text = ' '.join(args).strip()
    if not query_text:
        ayuda = "Uso: !ia <pregunta de emergencia> (ej: !ia picadura de medusa) o !ia reset para nueva conversación."
        interface.reply_to_message(ayuda, metadata)
        return

    # Encolar petición en hilo worker
    try:
        _ia_queue.put_nowait({
            "tipo": "consulta",
            "consulta": query_text,
            "interface": interface,
            "metadata": metadata,
            "from_id": from_id,
        })
        _ensure_worker_running()
    except queue.Full:
        log_p(f"[IA] Cola de IA llena ({_MAX_QUEUE_SIZE}), rechazando petición de {from_id}", level="WARN")
        interface.reply_to_message("⚠️ Cola de peticiones de IA ocupada, inténtalo en un minuto.", metadata)
