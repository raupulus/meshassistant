from __future__ import annotations
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import env
from functions import log_p
from Models.Database import Database


class AntiAbuseManager:
    """Control de saturación y prevención de abusos en la recepción de comandos."""

    def __init__(self) -> None:
        self.db = Database()
        # Ventana deslizante en memoria: node_id -> deque de timestamps (float epoch)
        self._history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=20))

    def _get_limits(self) -> Tuple[int, int]:
        max_cmds = int(getattr(env, "RATE_LIMIT_MAX_PER_MINUTE", 10) or 10)
        ban_mins = int(getattr(env, "RATE_LIMIT_BAN_MINUTES", 15) or 15)
        return max_cmds, ban_mins

    def is_allowed(
        self,
        node_id: str,
        command: Optional[str] = None,
        node_name: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Verifica si un nodo tiene permitido ejecutar un comando.

        Retorna (allowed, reason). Si no está permitido, allowed es False.
        """
        if not node_id:
            return True, None

        # 0. Comprobar si está marcado como ignorado en el sistema de vigilancia
        try:
            from Models.MeshWatcher import MeshWatcher
            if MeshWatcher.is_ignored(node_id):
                log_p(f"[AntiAbuse] Descartado comando '{command}' de {node_id}: nodo ignorado en bot", level="DEBUG")
                return False, "Nodo ignorado en bot"
        except Exception:
            pass

        # 1. Comprobar lista negra en base de datos (bloqueos manuales o automáticos activos)
        blocked, info = self.db.is_node_blocked(node_id)
        if blocked:
            reason = (info or {}).get("reason") or "Nodo bloqueado"
            log_p(f"[AntiAbuse] Descartado comando '{command}' de {node_id} ({node_name or 'N/D'}): {reason}", level="DEBUG")
            return False, reason

        # 2. Rate limiting por ventana deslizante (60 segundos)
        max_cmds, ban_mins = self._get_limits()
        now_ts = time.time()
        window_start = now_ts - 60.0

        q = self._history[node_id]
        # Limpiar eventos fuera de la ventana de 60s
        while q and q[0] < window_start:
            q.popleft()

        # Si supera el umbral en 60 segundos -> disparar auto-bloqueo
        if len(q) >= max_cmds:
            # Comprobar reincidencias en últimas 24h
            recent_abuses = self.db.get_abuse_logs(limit=20)
            repeat_count = sum(1 for a in recent_abuses if a.get("node_id") == node_id)
            
            if repeat_count >= 2:
                # Reincidente: bloqueo largo de 24 horas
                ban_duration = timedelta(hours=24)
                ban_action = "autoban_24h"
                reason_str = f"Saturación reincidente de comandos (> {max_cmds}/min en ventana)"
            else:
                # Primer aviso: bloqueo temporal de ban_mins minutos
                ban_duration = timedelta(minutes=ban_mins)
                ban_action = f"autoban_{ban_mins}m"
                reason_str = f"Exceso de comandos (> {max_cmds} en 60s)"

            expires_at = (datetime.now() + ban_duration).isoformat(timespec="seconds")

            self.db.block_node(
                node_id=node_id,
                node_name=node_name,
                block_type="auto",
                reason=reason_str,
                expires_at=expires_at,
            )
            self.db.log_abuse(
                node_id=node_id,
                command=command,
                action_taken=ban_action,
                reason=reason_str,
            )

            # Auto-reportar en el sistema de vigilancia
            try:
                from Models.MeshWatcher import MeshWatcher
                MeshWatcher.report_command_spam(node_id, len(q) + 1, name=node_name)
            except Exception:
                pass

            # Notificar en tiempo real por IPC a la interfaz web
            try:
                from Models.EventBroadcaster import broadcast_event
                broadcast_event("node_blocked", {
                    "node_id": node_id,
                    "node_name": node_name,
                    "block_type": "auto",
                    "action": ban_action,
                    "reason": reason_str,
                    "expires_at": expires_at,
                })
            except Exception:
                pass

            log_p(f"[AntiAbuse] Auto-bloqueo aplicado a {node_id} ({node_name or 'N/D'}): {reason_str} hasta {expires_at}", level="WARN")
            return False, reason_str

        # Registrar la ejecución actual
        q.append(now_ts)
        return True, None


# Instancia singleton para compartir la ventana en memoria durante el ciclo del daemon
anti_abuse_manager = AntiAbuseManager()
