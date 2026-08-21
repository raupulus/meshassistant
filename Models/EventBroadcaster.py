from __future__ import annotations

import json
import os
import socket
from datetime import datetime
from typing import Any, Dict, Optional

from functions import log_p

# Ruta por defecto del socket Unix DGRAM para eventos IPC
DEFAULT_EVENTS_SOCKET_PATH = "/tmp/meshassistant_events.sock"


class EventBroadcaster:
    """Emisor ligero y no bloqueante de eventos IPC mediante Unix Domain Sockets DGRAM.

    Diseñado para emitir eventos en microsegundos desde callbacks y bucles de radio sin
    bloquear ni depender de que el servidor WebSocket esté levantado.
    """

    _instance: Optional[EventBroadcaster] = None

    def __init__(self, socket_path: Optional[str] = None) -> None:
        import env as _env
        self.target_socket_path = (
            socket_path
            or getattr(_env, "GATEWAY_EVENTS_SOCKET", None)
            or DEFAULT_EVENTS_SOCKET_PATH
        )
        self._sock: Optional[socket.socket] = None

    @classmethod
    def get_instance(cls) -> EventBroadcaster:
        """Obtiene o crea la instancia singleton del broadcaster."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_socket(self) -> socket.socket:
        """Obtiene o recrea el socket Unix DGRAM en modo no bloqueante."""
        if self._sock is None:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.setblocking(False)
            self._sock = sock
        return self._sock

    def broadcast(
        self,
        event: str,
        data: Dict[str, Any],
        ts: Optional[str] = None,
    ) -> bool:
        """Emite un evento estructurado por el socket Unix.

        Retorna True si el paquete se envió correctamente, o False si el socket
        destino no está escuchando o hubo un error (sin lanzar excepciones).
        """
        try:
            if not os.path.exists(self.target_socket_path):
                # El receptor (Gateway) no está activo; descartar de inmediato
                return False

            now_iso = ts or datetime.now().isoformat(timespec="seconds")
            payload = {
                "event": event,
                "ts": now_iso,
                "data": data,
            }
            raw_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

            sock = self._get_socket()
            sock.sendto(raw_bytes, self.target_socket_path)
            return True
        except (BlockingIOError, FileNotFoundError, ConnectionRefusedError, OSError):
            # El servidor WS puede estar ocupado, reiniciándose o no presente.
            # No interrumpir jamás el hilo emisor de radio.
            return False
        except Exception as e:
            log_p(f"EventBroadcaster error: {e}", level="DEBUG")
            return False

    def close(self) -> None:
        """Cierra el socket si estuviera abierto."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            finally:
                self._sock = None


def broadcast_event(event: str, data: Dict[str, Any], ts: Optional[str] = None) -> bool:
    """Función de conveniencia para emitir un evento con el singleton."""
    return EventBroadcaster.get_instance().broadcast(event, data, ts)
