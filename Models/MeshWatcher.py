from __future__ import annotations

import time
from typing import Any, Dict, Optional, Set
from functions import log_p
from Models.Database import Database


class MeshWatcher:
    """Sistema de vigilancia de malla LoRa para Raspberry Pi Zero.
    
    Rastrea en memoria RAM las marcas de tiempo de telemetría y saltos iniciales
    para detectar comportamientos perjudiciales con coste computacional casi nulo:
    - Saltos iniciales configurados >= 6 (hopStart / hopLimit).
    - Telemetrías frecuentes (< 30 min por tipo: Batería, Posición, NodeInfo, Sensores).
    - Nodos ignorados / bloqueados en el bot.
    """

    MIN_TELEMETRY_INTERVAL_SEC = 1800  # 30 minutos (1800 segundos)
    MAX_RECOMMENDED_HOPS = 5          # Saltos máximos saludables

    PORT_MAP = {
        "TELEMETRY_APP": ("FAST_TELEMETRY", "Telemetría de batería / dispositivo"),
        "POSITION_APP": ("FAST_POSITION", "Posición GPS / Coordenadas"),
        "NODEINFO_APP": ("FAST_NODEINFO", "Difusión de NodeInfo / Usuario"),
        "ENVIRONMENTAL_MEASUREMENT_APP": ("FAST_ENVIRONMENTAL", "Sensores ambientales / Clima"),
    }

    _last_telemetry: Dict[str, Dict[str, float]] = {}
    _ignored_nodes: Set[str] = set()
    _initialized: bool = False

    @classmethod
    def init(cls) -> None:
        """Inicializa la lista de nodos ignorados desde la base de datos."""
        try:
            db = Database()
            cls._ignored_nodes = db.get_ignored_node_ids()
            cls._initialized = True
            log_p(f"[Watcher] Inicializado con {len(cls._ignored_nodes)} nodos ignorados", level="DEBUG")
        except Exception as e:
            cls._ignored_nodes = set()
            cls._initialized = True
            log_p(f"[Watcher] Error inicializando nodos ignorados: {e}", level="WARN")

    @classmethod
    def is_ignored(cls, node_id: Optional[str]) -> bool:
        """Devuelve True si el nodo está en la lista de ignorados del bot."""
        if not node_id:
            return False
        if not cls._initialized:
            cls.init()
        return str(node_id).strip() in cls._ignored_nodes

    @classmethod
    def set_ignored(cls, node_id: str, is_ignored: bool = True) -> None:
        """Actualiza el estado de ignorado en memoria y base de datos."""
        if not node_id:
            return
        if not cls._initialized:
            cls.init()
        nid = str(node_id).strip()
        if is_ignored:
            cls._ignored_nodes.add(nid)
        else:
            cls._ignored_nodes.discard(nid)
        try:
            Database().set_node_bot_ignored(nid, is_ignored)
            # Notificar evento a la pasarela WiFi
            try:
                from Models.EventBroadcaster import broadcast_event
                broadcast_event("node_ignore_toggled", {
                    "node_id": nid,
                    "is_ignored": is_ignored,
                })
            except Exception:
                pass
        except Exception as e:
            log_p(f"[Watcher] Error guardando estado ignorado para {nid}: {e}", level="WARN")

    @classmethod
    def inspect_packet(cls, packet: Dict[str, Any], from_node_info: Optional[Any] = None) -> bool:
        """Inspecciona un paquete en microsegundos.
        
        Devuelve:
            bool: True si el paquete debe ser DESCARTADO (nodo ignorado),
                  False si el paquete es legítimo y debe ser procesado.
        """
        if not isinstance(packet, dict):
            return False

        if not cls._initialized:
            cls.init()

        # 1. Resolver identificador del emisor
        from_id = packet.get("fromId")
        from_num = packet.get("from")
        if not from_id and from_num is not None:
            try:
                from_id = f"!{int(from_num):08x}"
            except Exception:
                from_id = str(from_num)

        if not from_id:
            return False

        from_id = str(from_id).strip()

        # 2. Si el nodo está marcado como ignorado, descartar inmediatamente
        if from_id in cls._ignored_nodes:
            log_p(f"[Watcher] Paquete descartado: nodo {from_id} está ignorado en bot", level="DEBUG")
            return True

        short_name = getattr(from_node_info, "short_name", None) if from_node_info else None
        name = getattr(from_node_info, "name", None) if from_node_info else None

        # 3. Comprobar exceso de saltos iniciales configurados (hopStart >= 6)
        h_start = packet.get("hopStart")
        h_limit = packet.get("hopLimit")
        configured_hops = None
        if h_start is not None:
            try:
                configured_hops = int(h_start)
            except Exception:
                configured_hops = None
        elif h_limit is not None:
            try:
                configured_hops = int(h_limit)
            except Exception:
                configured_hops = None

        if configured_hops is not None and configured_hops > cls.MAX_RECOMMENDED_HOPS:
            # Registrar incidencia por configuración de saltos excesivos
            try:
                db = Database()
                db.record_auto_reported_node(
                    node_id=from_id,
                    reason_code="EXCESSIVE_HOPS",
                    reason_desc=f"Configurado con {configured_hops} saltos iniciales (máx recomendado 3-5)",
                    details={
                        "hop_start": h_start,
                        "hop_limit": h_limit,
                        "configured_hops": configured_hops,
                        "max_allowed": cls.MAX_RECOMMENDED_HOPS,
                    },
                    short_name=short_name,
                    name=name,
                )
                try:
                    from Models.EventBroadcaster import broadcast_event
                    broadcast_event("auto_report_event", {
                        "node_id": from_id,
                        "reason_code": "EXCESSIVE_HOPS",
                        "short_name": short_name,
                    })
                except Exception:
                    pass
            except Exception as e:
                log_p(f"[Watcher] Error registrando salto excesivo: {e}", level="WARN")

        # 4. Comprobar cadencia de telemetría (< 30 min)
        decoded = packet.get("decoded", {}) if isinstance(packet.get("decoded"), dict) else {}
        portnum = decoded.get("portnum")
        if not portnum and "telemetry" in packet:
            portnum = "TELEMETRY_APP"

        if portnum and portnum in cls.PORT_MAP:
            reason_code, port_label = cls.PORT_MAP[portnum]
            now_ts = time.time()

            if from_id not in cls._last_telemetry:
                cls._last_telemetry[from_id] = {}

            last_ts = cls._last_telemetry[from_id].get(portnum)
            cls._last_telemetry[from_id][portnum] = now_ts

            if last_ts is not None:
                delta_sec = int(now_ts - last_ts)
                if delta_sec < cls.MIN_TELEMETRY_INTERVAL_SEC:
                    # Formatear tiempo legible (ej. 120s o 2m 5s)
                    time_str = f"{delta_sec}s" if delta_sec < 60 else f"{delta_sec // 60}m {delta_sec % 60}s"
                    desc = f"{port_label} emitida cada {time_str} (mínimo recomendado 30m / 1800s)"
                    try:
                        db = Database()
                        db.record_auto_reported_node(
                            node_id=from_id,
                            reason_code=reason_code,
                            reason_desc=desc,
                            details={
                                "portnum": portnum,
                                "interval_sec": delta_sec,
                                "min_interval_sec": cls.MIN_TELEMETRY_INTERVAL_SEC,
                            },
                            short_name=short_name,
                            name=name,
                        )
                        try:
                            from Models.EventBroadcaster import broadcast_event
                            broadcast_event("auto_report_event", {
                                "node_id": from_id,
                                "reason_code": reason_code,
                                "short_name": short_name,
                            })
                        except Exception:
                            pass
                    except Exception as e:
                        log_p(f"[Watcher] Error registrando telemetría rápida: {e}", level="WARN")

        return False

    @classmethod
    def report_command_spam(cls, node_id: str, count_1m: int, short_name: Optional[str] = None, name: Optional[str] = None) -> None:
        """Registra una incidencia de saturación de comandos."""
        if not node_id:
            return
        desc = f"Saturación de comandos: {count_1m} peticiones en 1 minuto (límite 10/min)"
        try:
            db = Database()
            db.record_auto_reported_node(
                node_id=str(node_id),
                reason_code="COMMAND_SPAM",
                reason_desc=desc,
                details={"commands_per_min": count_1m, "threshold": 10},
                short_name=short_name,
                name=name,
            )
            try:
                from Models.EventBroadcaster import broadcast_event
                broadcast_event("auto_report_event", {
                    "node_id": node_id,
                    "reason_code": "COMMAND_SPAM",
                    "short_name": short_name,
                })
            except Exception:
                pass
        except Exception as e:
            log_p(f"[Watcher] Error registrando spam de comandos: {e}", level="WARN")
