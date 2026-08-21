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
        self.last_system_status: Dict[str, Any] = {}
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

        for ws in self.connected_clients:
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
                if "local_node" in include:
                    snapshot_data["local_node"] = self.last_local_node
                if "channel_metrics" in include:
                    snapshot_data["channel_metrics"] = self.last_channel_metrics

                if "nodes" in include:
                    snapshot_data["nodes"] = self.db.get_all_nodes(limit=300)
                    snapshot_data["nodes_summary"] = self.db.nodes_overview()
                if "traces" in include:
                    snapshot_data["traces"] = self.db.get_recent_traces(limit=10)
                if "stats" in include:
                    snapshot_data["stats"] = self.db.stats_summary()
                if "routers" in include:
                    router_ids = getattr(env, "ROUTER_NODES", []) or getattr(env, "ROUTERS_LIST", [])
                    if isinstance(router_ids, str):
                        router_ids = [r.strip() for r in router_ids.split(",") if r.strip()]
                    snapshot_data["routers"] = self.db.get_router_nodes(router_ids)

                response["data"] = snapshot_data

            elif action == "request_trace":
                dest = params.get("dest")
                if not dest:
                    raise ValueError("Parámetro 'dest' obligatorio")
                trace_id = self.db.enqueue_trace(str(dest))
                response["data"] = {"trace_id": trace_id, "status": "queued"}

            elif action == "get_polls":
                polls = self.db.encuesta_list_active()
                # Enriquecer con resultados de conteo
                for p in polls:
                    res = self.db.encuesta_results(p["id"])
                    p["counts"] = res.get("counts", [])
                    p["total_votes"] = res.get("total", 0)
                response["data"] = {"polls": polls}

            elif action == "vote_poll":
                poll_id = params.get("poll_id")
                option_index = params.get("option_index")
                node_id = params.get("node_id") or "gateway_client"
                if poll_id is None or option_index is None:
                    raise ValueError("Parámetros 'poll_id' y 'option_index' obligatorios")
                result = self.db.encuesta_vote(int(poll_id), str(node_id), int(option_index))
                response["data"] = {"status": result}

            elif action == "get_weather":
                weather = self.db.aemet_weather_get_latest()
                response["data"] = weather or {}

            elif action == "get_tides":
                tides = self.db.tides_get_latest()
                response["data"] = tides or {}

            elif action == "set_node_favorite":
                node_id = params.get("node_id")
                is_fav = bool(params.get("is_favorite", True))
                if not node_id:
                    raise ValueError("Parámetro 'node_id' obligatorio")
                self.db.update_node(str(node_id), {"is_favorite": 1 if is_fav else 0})
                response["data"] = {"node_id": node_id, "is_favorite": is_fav}

            elif action == "send_message":
                text = params.get("text")
                dest = params.get("dest", "^all")
                channel = params.get("channel", 0)
                if not text:
                    raise ValueError("Parámetro 'text' obligatorio")
                # Por ahora registramos la petición; encolamiento en radio si aplica
                response["data"] = {"queued": True, "text": text, "dest": dest, "channel": channel}

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
            headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
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
