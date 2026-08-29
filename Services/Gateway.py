from __future__ import annotations

import asyncio
import json
import os
import socket
from collections import deque
from datetime import datetime
from typing import Any, Dict, Optional, Set
import websockets

import sys
from pathlib import Path

# Asegurar raíz del proyecto en sys.path al ejecutarse directamente como servicio
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import env
from functions import log_p
from Models.Database import Database

# Constantes y configuración por defecto
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8680
DEFAULT_SOCKET_PATH = "/tmp/meshassistant_events.sock"
MAX_RECENT_MESSAGES = 20


class UnixSocketProtocol(asyncio.DatagramProtocol):
    """Protocolo asíncrono para recibir datagramas JSON desde el Unix Domain Socket."""

    def __init__(self, gateway: GatewayService) -> None:
        self.gateway = gateway

    def datagram_received(self, data: bytes, addr: Any) -> None:
        try:
            raw_text = data.decode("utf-8")
            event_obj = json.loads(raw_text)
            self.gateway.on_ipc_event(event_obj)
        except Exception as e:
            log_p(f"[Gateway IPC] Error procesando datagrama: {e}", level="WARN")

    def error_received(self, exc: Exception) -> None:
        log_p(f"[Gateway IPC] Error en socket: {exc}", level="WARN")


class GatewayService:
    """Servidor de pasarela WebSocket e IPC para Meshassistant."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        socket_path: Optional[str] = None,
    ) -> None:
        self.host = host or getattr(env, "GATEWAY_WS_HOST", DEFAULT_HOST)
        self.port = int(port or getattr(env, "GATEWAY_WS_PORT", DEFAULT_PORT))
        self.socket_path = socket_path or getattr(
            env, "GATEWAY_EVENTS_SOCKET", DEFAULT_SOCKET_PATH
        )
        self.api_token = getattr(env, "GATEWAY_API_TOKEN", None)

        # Clientes WebSocket conectados
        self.connected_clients: Set[websockets.WebSocketServerProtocol] = set()

        # Buffer circular en memoria RAM para mensajes recientes (cero escrituras en BD)
        self.recent_messages: deque = deque(maxlen=MAX_RECENT_MESSAGES)

        # Último estado conocido en memoria
        serial_path = getattr(env, 'SERIAL_DEVICE_PATH', '/dev/serial0')
        self.last_system_status: Dict[str, Any] = {
            "uart_connected": os.path.exists(serial_path) if isinstance(serial_path, str) else True,
            "serial_port": serial_path,
        }
        self.last_system_telemetry: Dict[str, Any] = {}
        self.last_local_node: Dict[str, Any] = {}
        self.last_channel_metrics: Dict[str, Any] = {}

        self.db = Database()
        self._running = False

    def on_ipc_event(self, event_obj: Dict[str, Any]) -> None:
        """Procesa un evento recibido por IPC y lo distribuye a los clientes."""
        event_name = event_obj.get("event")
        data = event_obj.get("data", {})

        # Actualizar estado en memoria RAM
        if event_name == "message_rx":
            self.recent_messages.append(event_obj)
        elif event_name == "system_status":
            self.last_system_status = data
        elif event_name == "system_telemetry":
            self.last_system_telemetry = data
        elif event_name == "local_node_info":
            self.last_local_node = data
        elif event_name == "channel_metrics":
            self.last_channel_metrics = data

        # Retransmitir a clientes WebSocket conectados si hay un bucle activo
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast_ws(event_obj))
        except RuntimeError:
            pass

    async def _broadcast_ws(self, event_obj: Dict[str, Any]) -> None:
        """Envía el evento JSON a todos los clientes WebSocket conectados."""
        if not self.connected_clients:
            return

        raw_json = json.dumps(event_obj, ensure_ascii=False)
        disconnected = set()

        for ws in list(self.connected_clients):
            try:
                await ws.send(raw_json)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(ws)
            except Exception as e:
                log_p(f"[Gateway WS] Error enviando a cliente: {e}", level="DEBUG")
                disconnected.add(ws)

        if disconnected:
            self.connected_clients.difference_update(disconnected)

    async def _handle_action(
        self,
        ws: websockets.WebSocketServerProtocol,
        request: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Procesa una acción enviada por un cliente WebSocket y devuelve la respuesta."""
        action = request.get("action")
        req_id = request.get("req_id")
        params = request.get("params", {})

        response: Dict[str, Any] = {
            "type": "response",
            "action": action,
            "req_id": req_id,
            "success": True,
            "data": None,
            "error": None,
        }

        try:
            if action == "get_snapshot":
                # Resumen de estado actual
                include = params.get("include", ["nodes", "routers", "recent_messages", "stats", "system_status", "local_node"])
                snapshot_data: Dict[str, Any] = {}

                if "recent_messages" in include:
                    snapshot_data["recent_messages"] = list(self.recent_messages)
                if "system_status" in include:
                    snapshot_data["system_status"] = self.last_system_status
                if "system_telemetry" in include or "system_status" in include:
                    snapshot_data["system_telemetry"] = self.last_system_telemetry
                if "local_node" in include:
                    snapshot_data["local_node"] = self.last_local_node
                if "channel_metrics" in include:
                    snapshot_data["channel_metrics"] = self.last_channel_metrics

                if "nodes" in include:
                    snapshot_data["nodes"] = self.db.get_all_nodes(limit=None)
                    snapshot_data["nodes_summary"] = self.db.nodes_overview()
                if "traces" in include:
                    snapshot_data["traces"] = self.db.get_recent_traces(limit=10)
                if "stats" in include:
                    snapshot_data["stats"] = self.db.stats_summary()
                snapshot_data["auto_reported_count"] = self.db.count_auto_reported_nodes()
                if "auto_reported" in include or "security" in include:
                    snapshot_data["auto_reported_nodes"] = self.db.get_auto_reported_nodes(limit=50)
                if "routers" in include:
                    router_ids = getattr(env, "ROUTER_NODES", []) or getattr(env, "ROUTERS_LIST", [])
                    if isinstance(router_ids, str):
                        router_ids = [r.strip() for r in router_ids.split(",") if r.strip()]
                    raw_routers = self.db.get_router_nodes(router_ids)
                    
                    # Enriquecer routers con estado online/offline y segundos desde última señal
                    enriched_routers = []
                    now_dt = datetime.now()
                    for node in raw_routers:
                        r = dict(node)
                        nid = r.get('node_id') or r.get('identifier') or r.get('id')
                        r['id'] = nid
                        r['name'] = r.get('short_name') or r.get('name') or nid or 'Router'
                        ts = r.get('last_heard') or r.get('updated_at')
                        diff_sec = None
                        if ts:
                            try:
                                if isinstance(ts, (int, float)) or str(ts).isdigit():
                                    dt = datetime.fromtimestamp(float(ts))
                                else:
                                    dt = datetime.fromisoformat(str(ts))
                                diff_sec = max(0, int((now_dt - dt).total_seconds()))
                            except Exception:
                                diff_sec = None
                        r['last_seen_sec'] = diff_sec
                        r['status'] = 'online' if (diff_sec is not None and diff_sec < 86400 and not r.get('offline')) else 'offline'
                        
                        # Enriquecer con información de trace real más reciente vía base RAU0
                        if nid:
                            try:
                                t_info = self.db.get_latest_trace_route_info(nid, base_identifiers=['RAU0'])
                                if t_info:
                                    r['trace_hops'] = t_info.get('hops')
                                    r['trace_snr_text'] = t_info.get('snr_text')
                                    r['trace_intermediates'] = t_info.get('intermediates', [])
                            except Exception:
                                pass

                        enriched_routers.append(r)
                    
                    snapshot_data["routers"] = enriched_routers

                # Incluir mapa de canales configurados
                try:
                    from data import channels
                    snapshot_data["channels"] = channels
                except Exception:
                    pass

                response["data"] = snapshot_data

            elif action == "request_trace":
                dest = params.get("dest")
                if not dest:
                    raise ValueError("Parámetro 'dest' obligatorio")
                trace_id = self.db.enqueue_trace(str(dest))
                response["data"] = {"trace_id": trace_id, "status": "queued"}

            elif action == "request_node_info":
                node_id = params.get("node_id") or params.get("dest")
                if not node_id:
                    raise ValueError("Parámetro 'node_id' obligatorio")
                outbox_id = self.db.enqueue_outbox("__REQ_NODEINFO__", dest=str(node_id), channel=0)
                response["data"] = {"queued": True, "outbox_id": outbox_id, "node_id": str(node_id)}

            elif action in ("request_telemetry", "request_battery"):
                node_id = params.get("node_id") or params.get("dest")
                if not node_id:
                    raise ValueError("Parámetro 'node_id' o 'dest' obligatorio")
                outbox_id = self.db.enqueue_outbox("__REQ_TELEMETRY__", dest=str(node_id), channel=0)
                response["data"] = {"queued": True, "outbox_id": outbox_id, "node_id": str(node_id)}

            elif action == "get_polls":
                polls = self.db.encuesta_list_all(limit=100)
                # Enriquecer con resultados de conteo
                for p in polls:
                    res = self.db.encuesta_results(p["id"])
                    p["counts"] = res.get("counts", [])
                    p["total_votes"] = res.get("total", 0)
                    p["results_detailed"] = res.get("results", [])
                response["data"] = {"polls": polls}

            elif action == "create_poll":
                question = params.get("question")
                raw_options = params.get("options")
                if not question or not raw_options:
                    raise ValueError("Parámetros 'question' y 'options' obligatorios")
                
                if isinstance(raw_options, str):
                    options = [o.strip() for o in raw_options.split(",") if o.strip()]
                elif isinstance(raw_options, list):
                    options = [str(o).strip() for o in raw_options if str(o).strip()]
                else:
                    raise ValueError("Formato de 'options' no válido")

                if len(options) < 2:
                    raise ValueError("La encuesta debe tener al menos 2 opciones")

                days = int(params.get("days", 7))
                starts_at = params.get("starts_at")
                ends_at = params.get("ends_at")
                owner_id = params.get("owner_node_id") or "web_admin"

                poll_id = self.db.encuesta_create(
                    owner_node_id=owner_id,
                    question=str(question),
                    options=options,
                    days=days,
                    starts_at=starts_at,
                    ends_at=ends_at,
                )

                # Publicación inicial en canales si se solicita
                publish_channels = params.get("publish_channels") or []
                if isinstance(publish_channels, (int, str)):
                    publish_channels = [int(publish_channels)]
                
                if publish_channels:
                    ops_str = " | ".join([f"{i+1}. {op}" for i, op in enumerate(options)])
                    announce_msg = f"🗳️ [Nueva Encuesta #{poll_id}] {question}\n{ops_str}\n👉 Vota con: /encuesta votar {poll_id} <1-{len(options)}>"
                    for ch in publish_channels:
                        try:
                            self.db.enqueue_outbox(announce_msg, dest="^all", channel=int(ch))
                        except Exception:
                            pass

                response["data"] = {"poll_id": poll_id, "success": True}

            elif action == "close_poll":
                poll_id = params.get("poll_id")
                if poll_id is None:
                    raise ValueError("Parámetro 'poll_id' obligatorio")
                ok = self.db.encuesta_close(int(poll_id), owner_node_id=None)
                response["data"] = {"poll_id": int(poll_id), "closed": ok}

            elif action == "delete_poll":
                poll_id = params.get("poll_id")
                if poll_id is None:
                    raise ValueError("Parámetro 'poll_id' obligatorio")
                ok = self.db.encuesta_delete(int(poll_id), owner_node_id=None)
                response["data"] = {"poll_id": int(poll_id), "deleted": ok}

            elif action == "publish_poll_reminder":
                poll_id = params.get("poll_id")
                channels = params.get("channels") or [0]
                frequency = params.get("frequency") or "once"
                if poll_id is None:
                    raise ValueError("Parámetro 'poll_id' obligatorio")
                if isinstance(channels, (int, str)):
                    channels = [int(channels)]

                poll = self.db.encuesta_get(int(poll_id))
                if not poll:
                    raise ValueError(f"Encuesta #{poll_id} no encontrada")

                options = poll.get("options") or []
                ops_str = " | ".join([f"{i+1}. {op}" for i, op in enumerate(options)])
                reminder_msg = (
                    f"🗳️ [Recordatorio Encuesta #{poll['id']}] {poll['question']}\n"
                    f"{ops_str}\n"
                    f"👉 Vota con: /encuesta votar {poll['id']} <1-{len(options)}>"
                )

                if frequency == "once":
                    for ch in channels:
                        self.db.enqueue_outbox(reminder_msg, dest="^all", channel=int(ch))
                else:
                    freq_map = {
                        "hourly": 3600,
                        "every_6h": 21600,
                        "every_12h": 43200,
                        "daily": 86400,
                        "weekly": 604800,
                    }
                    interval_sec = freq_map.get(frequency, 86400)
                    for ch in channels:
                        sched_name = f"Recordatorio Encuesta #{poll_id} (Ch {ch})"
                        self.db.schedule_message_create(
                            name=sched_name,
                            text=reminder_msg,
                            channel=int(ch),
                            dest="^all",
                            cron_exp=None,
                            interval_seconds=interval_sec,
                            enabled=True,
                        )

                response["data"] = {
                    "success": True,
                    "poll_id": int(poll_id),
                    "channels": channels,
                    "frequency": frequency,
                    "reminder_text": reminder_msg,
                }

            elif action == "vote_poll":
                poll_id = params.get("poll_id")
                option_index = params.get("option_index")
                node_id = params.get("node_id") or "gateway_client"
                if poll_id is None or option_index is None:
                    raise ValueError("Parámetros 'poll_id' y 'option_index' obligatorios")
                result = self.db.encuesta_vote(int(poll_id), str(node_id), int(option_index))
                response["data"] = {"status": result}

            elif action in ("get_weather", "get_weather_full"):
                # 1. Ubicaciones multi-día
                locations = self.db.aemet_forecast_daily_get_all_latest()
                if not locations:
                    single = self.db.aemet_forecast_daily_get_latest()
                    if single:
                        locations = [single]

                # 2. Textos meteorológicos por provincia/municipio
                weather_texts = self.db.aemet_weather_get_all_latest()
                if not weather_texts:
                    single_w = self.db.aemet_weather_get_latest()
                    if single_w:
                        weather_texts = [single_w]

                # 3. Predicción horaria
                hourly = self.db.aemet_forecast_hourly_get_latest() or {}

                # 4. Mareas
                tides = self.db.tides_get_latest() or {}

                # 5. Astronomía: Sol y Luna (cálculo instantáneo offline)
                sun_data = {}
                moon_data = {}
                try:
                    from Models.Astro import sun_info, moon_phase, next_phase_dates
                    s_info = sun_info()
                    sr = s_info.get("sunrise")
                    ss = s_info.get("sunset")
                    sun_len = s_info.get("day_length")
                    sun_data = {
                        "name": s_info.get("name", "Zona Local"),
                        "sunrise": sr.strftime("%H:%M") if sr else "--:--",
                        "sunset": ss.strftime("%H:%M") if ss else "--:--",
                        "day_length": f"{int(sun_len.total_seconds()//3600)}h {int((sun_len.total_seconds()%3600)//60):02d}m" if sun_len else "--",
                    }

                    m_phase = moon_phase()
                    m_nxt = next_phase_dates()
                    nxt_f = m_nxt.get("next_full")
                    nxt_n = m_nxt.get("next_new")
                    moon_data = {
                        "phase_name": m_phase.get("phase_name", "Luna"),
                        "illumination_pct": int(round(m_phase.get("illumination", 0) * 100)),
                        "waxing": bool(m_phase.get("waxing")),
                        "tendency": "creciente" if m_phase.get("waxing") else "menguante",
                        "next_full": nxt_f.strftime("%d/%m") if nxt_f else "--",
                        "next_new": nxt_n.strftime("%d/%m") if nxt_n else "--",
                    }
                except Exception as e:
                    log_p(f"[Gateway] Error calculando sol/luna: {e}", level="DEBUG")

                # 6. Maremoto / Sismología histórica
                from datetime import date
                from calendar import monthrange
                today = date.today()
                ref_date = date(1755, 11, 1)
                years = today.year - ref_date.year
                months = today.month - ref_date.month
                days = today.day - ref_date.day
                if days < 0:
                    months -= 1
                    prev_m = today.month - 1 if today.month > 1 else 12
                    prev_y = today.year if today.month > 1 else today.year - 1
                    days += monthrange(prev_y, prev_m)[1]
                if months < 0:
                    years -= 1
                    months += 12
                tsunami_data = {
                    "last_event_date": "1755-11-01",
                    "location": "Golfo de Cádiz / Chipiona",
                    "years": years,
                    "months": months,
                    "days": days,
                    "status": "Vigilancia normal",
                    "info": f"Han pasado {years} años, {months} meses y {days} días desde el último gran maremoto en Cádiz y Chipiona (1/11/1755).",
                }

                # 7. Alertas AEMET activas
                alerts = self.db.aemet_get_recent_alerts(limit=5, hours=48)

                # 8. Previsión Marítima
                maritime = self.db.aemet_maritime_get_latest() or {}

                response["data"] = {
                    "locations": locations,
                    "weather_texts": weather_texts,
                    "hourly": hourly,
                    "tides": tides,
                    "sun": sun_data,
                    "moon": moon_data,
                    "tsunami": tsunami_data,
                    "alerts": alerts,
                    "maritime": maritime,
                }

            elif action == "get_tides":
                tides = self.db.tides_get_latest()
                response["data"] = tides or {}

            elif action == "set_node_favorite":
                node_id = params.get("node_id")
                is_fav = bool(params.get("is_favorite", True))
                if not node_id:
                    raise ValueError("Parámetro 'node_id' obligatorio")
                self.db.update_node(str(node_id), {"is_favorite": is_fav})
                response["data"] = {"node_id": node_id, "is_favorite": is_fav}

            elif action == "send_message":
                text = params.get("text")
                dest = params.get("dest", "^all")
                channel = params.get("channel", 0)
                if not text:
                    raise ValueError("Parámetro 'text' obligatorio")
                
                # Encolar en outbox para que main.py lo transmita por serie/radio
                outbox_id = self.db.enqueue_outbox(str(text), dest=str(dest), channel=int(channel))
                response["data"] = {
                    "queued": True,
                    "outbox_id": outbox_id,
                    "text": text,
                    "dest": dest,
                    "channel": int(channel)
                }

            elif action == "get_commands_audit":
                h_param = params.get("hours", 24)
                hours = None if (h_param in (None, 'all', 'None', 0)) else int(h_param)
                limit = int(params.get("limit", 100))
                offset = int(params.get("offset", 0))
                node_id = params.get("node_id")
                cmd = params.get("command")
                response["data"] = {
                    "ranking": self.db.get_top_command_users(limit=20, hours=hours),
                    "recent_logs": self.db.get_commands_audit(limit=limit, offset=offset, hours=hours, node_id=node_id, command=cmd),
                    "summary": self.db.get_commands_audit_summary(hours=hours),
                    "offset": offset,
                    "limit": limit,
                }

            elif action == "get_scheduled_messages":
                msgs = self.db.get_scheduled_messages(limit=100)
                response["data"] = {"messages": msgs}

            elif action == "create_scheduled_message":
                text = params.get("message")
                if not text:
                    raise ValueError("Parámetro 'message' obligatorio")
                chs = params.get("channels", "all")
                p_type = params.get("period_type", "hours")
                p_val = int(params.get("period_value", 1))
                start_at = params.get("start_at")
                enabled = 1 if params.get("enabled", True) else 0
                msg_id = self.db.create_scheduled_message(
                    message=text,
                    channels=chs,
                    period_type=p_type,
                    period_value=p_val,
                    start_at=start_at,
                    enabled=enabled,
                )
                response["data"] = {"id": msg_id, "created": True}

            elif action == "update_scheduled_message":
                msg_id = params.get("id")
                if not msg_id:
                    raise ValueError("Parámetro 'id' obligatorio")
                data_up = params.get("data")
                if not isinstance(data_up, dict):
                    data_up = {k: v for k, v in params.items() if k not in ("id", "action")}
                ok = self.db.update_scheduled_message(int(msg_id), data_up)
                response["data"] = {"id": msg_id, "updated": ok}

            elif action == "toggle_scheduled_message":
                msg_id = params.get("id")
                if not msg_id:
                    raise ValueError("Parámetro 'id' obligatorio")
                en = 1 if params.get("enabled", True) else 0
                ok = self.db.update_scheduled_message(int(msg_id), {"enabled": en})
                response["data"] = {"id": msg_id, "enabled": bool(en), "success": ok}

            elif action == "delete_scheduled_message":
                msg_id = params.get("id")
                if not msg_id:
                    raise ValueError("Parámetro 'id' obligatorio")
                ok = self.db.delete_scheduled_message(int(msg_id))
                response["data"] = {"id": msg_id, "deleted": ok}

            elif action == "get_blocked_nodes":
                nodes = self.db.get_blocked_nodes(active_only=False)
                response["data"] = {"blocked_nodes": nodes}

            elif action == "block_node_manual":
                node_id = params.get("node_id")
                if not node_id:
                    raise ValueError("Parámetro 'node_id' obligatorio")
                node_name = params.get("node_name")
                reason = params.get("reason") or "Bloqueo manual administrativo"
                expires_at = params.get("expires_at")  # None = permanente
                self.db.block_node(
                    node_id=str(node_id),
                    node_name=node_name,
                    block_type="manual",
                    reason=reason,
                    expires_at=expires_at,
                )
                self.db.log_abuse(
                    node_id=str(node_id),
                    command=None,
                    action_taken="manual_block",
                    reason=reason,
                )
                response["data"] = {"node_id": node_id, "blocked": True}

            elif action == "unblock_node":
                node_id = params.get("node_id")
                if not node_id:
                    raise ValueError("Parámetro 'node_id' obligatorio")
                ok = self.db.unblock_node(str(node_id))
                response["data"] = {"node_id": node_id, "unblocked": ok}

            elif action == "get_abuse_logs":
                limit = int(params.get("limit", 50))
                logs = self.db.get_abuse_logs(limit=limit)
                response["data"] = {"logs": logs}

            elif action == "get_auto_reported_nodes":
                limit = int(params.get("limit", 100))
                offset = int(params.get("offset", 0))
                reason = params.get("reason_code")
                nodes = self.db.get_auto_reported_nodes(limit=limit, offset=offset, reason_code=reason)
                total = self.db.count_auto_reported_nodes()
                response["data"] = {"auto_reported_nodes": nodes, "total": total}

            elif action == "set_node_bot_ignored":
                node_id = params.get("node_id")
                if not node_id:
                    raise ValueError("Parámetro 'node_id' obligatorio")
                is_ignored = bool(params.get("is_ignored", True))
                try:
                    from Models.MeshWatcher import MeshWatcher
                    MeshWatcher.set_ignored(str(node_id), is_ignored)
                except Exception:
                    self.db.set_node_bot_ignored(str(node_id), is_ignored)
                response["data"] = {"node_id": node_id, "is_ignored": is_ignored, "success": True}

            elif action == "set_node_fw_blocked":
                node_id = params.get("node_id")
                if not node_id:
                    raise ValueError("Parámetro 'node_id' obligatorio")
                is_blocked = bool(params.get("is_blocked", True))
                ok = self.db.set_node_fw_blocked(str(node_id), is_blocked)
                response["data"] = {"node_id": node_id, "is_blocked": is_blocked, "success": ok}

            elif action == "restart_serial":
                response["data"] = {"requested": True, "message": "Solicitud de reinicio de enlace serie registrada"}

            else:
                raise ValueError(f"Acción desconocida: '{action}'")

        except Exception as e:
            response["success"] = False
            response["error"] = str(e)

        return response

    async def _ws_handler(
        self,
        ws: websockets.WebSocketServerProtocol,
        *args: Any,
    ) -> None:
        """Maneja la conexión y ciclo de vida de un cliente WebSocket."""
        # Validación opcional de token
        if self.api_token:
            # Comprobar token en query string o header
            pass

        self.connected_clients.add(ws)
        remote_addr = getattr(ws, "remote_address", "desconocido")
        log_p(f"[Gateway WS] Cliente conectado: {remote_addr}")

        try:
            # Enviar mensaje de bienvenida
            welcome_msg = {
                "event": "welcome",
                "ts": datetime.now().isoformat(timespec="seconds"),
                "data": {
                    "version": "1.0",
                    "server": "meshassistant-gateway",
                    "local_node": self.last_local_node,
                    "system_status": self.last_system_status,
                },
            }
            await ws.send(json.dumps(welcome_msg, ensure_ascii=False))

            async for message in ws:
                try:
                    request = json.loads(message)
                    if isinstance(request, dict):
                        response = await self._handle_action(ws, request)
                        await ws.send(json.dumps(response, ensure_ascii=False))
                except json.JSONDecodeError:
                    err_resp = {
                        "type": "response",
                        "success": False,
                        "error": "Payload no es un JSON válido",
                    }
                    await ws.send(json.dumps(err_resp, ensure_ascii=False))
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            log_p(f"[Gateway WS] Error en handler de cliente: {e}", level="DEBUG")
        finally:
            self.connected_clients.discard(ws)
            log_p(f"[Gateway WS] Cliente desconectado: {remote_addr}")

    def _process_http_request(self, connection: Any, request: Any) -> Optional[Any]:
        """Procesa peticiones HTTP entrantes para servir la SPA del mini dashboard de forma 100% offline."""
        # Si es una petición de WebSocket upgrade, permitir que continúe el handshake
        upgrade_hdr = request.headers.get("Upgrade", "").lower()
        conn_hdr = request.headers.get("Connection", "").lower()
        if "websocket" in upgrade_hdr or "upgrade" in conn_hdr:
            return None

        # Petición HTTP estándar
        from websockets.http11 import Response, Headers

        path = request.path.split("?")[0]
        if path == "/" or not path:
            path = "/index.html"

        # Resolver ruta segura dentro del directorio web/
        web_dir = os.path.abspath(os.path.join(BASE_DIR, "web"))
        requested_file = os.path.abspath(os.path.join(web_dir, path.lstrip("/")))

        # Prevención de Directory Traversal y comprobación de existencia
        if not requested_file.startswith(web_dir) or not os.path.isfile(requested_file):
            headers = Headers()
            headers["Content-Type"] = "text/plain; charset=utf-8"
            return Response(404, "Not Found", headers, b"404 Not Found")

        # Determinar MIME type adecuado
        content_type = "application/octet-stream"
        if requested_file.endswith(".html"):
            content_type = "text/html; charset=utf-8"
        elif requested_file.endswith(".js"):
            content_type = "application/javascript; charset=utf-8"
        elif requested_file.endswith(".css"):
            content_type = "text/css; charset=utf-8"
        elif requested_file.endswith(".svg"):
            content_type = "image/svg+xml"
        elif requested_file.endswith(".json"):
            content_type = "application/json; charset=utf-8"
        elif requested_file.endswith(".png"):
            content_type = "image/png"
        elif requested_file.endswith(".ico"):
            content_type = "image/x-icon"

        try:
            with open(requested_file, "rb") as f:
                body = f.read()

            headers = Headers()
            headers["Content-Type"] = content_type
            headers["Content-Length"] = str(len(body))
            headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            headers["Pragma"] = "no-cache"
            headers["Expires"] = "0"
            return Response(200, "OK", headers, body)
        except Exception as e:
            log_p(f"[Gateway HTTP] Error leyendo archivo {requested_file}: {e}", level="WARN")
            headers = Headers()
            headers["Content-Type"] = "text/plain; charset=utf-8"
            return Response(500, "Internal Server Error", headers, b"500 Internal Server Error")

    async def start(self) -> None:
        """Inicia el servidor WebSocket y el receptor Unix Socket."""
        self._running = True
        loop = asyncio.get_running_loop()

        # 1. Configurar y limpiar socket Unix DGRAM
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass

        unix_sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        unix_sock.bind(self.socket_path)
        unix_sock.setblocking(False)

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: UnixSocketProtocol(self),
            sock=unix_sock,
        )
        log_p(f"[Gateway] Escuchando eventos IPC en {self.socket_path}")

        # 2. Iniciar servidor WebSocket TCP con soporte HTTP estático
        server = await websockets.serve(
            self._ws_handler,
            self.host,
            self.port,
            process_request=self._process_http_request,
        )
        log_p(f"[Gateway] Servidor WebSocket y Web UI activos en http://{self.host}:{self.port}")

        try:
            await asyncio.Future()  # Mantener corriendo
        finally:
            server.close()
            await server.wait_closed()
            transport.close()
            if os.path.exists(self.socket_path):
                try:
                    os.unlink(self.socket_path)
                except OSError:
                    pass


def main() -> None:
    """Punto de entrada principal para el daemon Gateway."""
    log_p("Iniciando servicio Meshassistant Gateway...")
    gateway = GatewayService()
    try:
        asyncio.run(gateway.start())
    except KeyboardInterrupt:
        log_p("Servicio Gateway detenido por el usuario.")


if __name__ == "__main__":
    main()
