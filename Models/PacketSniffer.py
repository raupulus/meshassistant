from __future__ import annotations

import time
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

from functions import log_p, now_utc_iso, to_utc_iso
from Models.Database import Database


class PacketSniffer:
    """Motor de inspección y captura selectiva de paquetes de radio LoRa.

    Filtra en memoria con impacto mínimo (microsegundos) para capturar paquetes
    con criterios de origen, destino, canal o administración remota PKI.
    """

    _rules_cache: List[Dict[str, Any]] = []
    _captured_nodes_cache: Set[str] = set()
    _last_cache_time: float = 0.0
    _CACHE_TTL: float = 10.0  # Recarga reglas de BD cada 10 segundos
    _recent_packet_ids: deque = deque(maxlen=300)

    @classmethod
    def reload_rules(cls) -> None:
        """Fuerza la recarga de reglas activas y nodos vigilados desde SQLite."""
        try:
            db = Database()
            cls._rules_cache = db.get_capture_rules(active_only=True)
            # Nodos con captura rápida individual activa
            nodes = db.get_all_nodes()
            cls._captured_nodes_cache = {
                str(n["node_id"]).strip()
                for n in nodes
                if n.get("is_captured") and n.get("node_id")
            }
            cls._last_cache_time = time.time()
        except Exception as e:
            log_p(f"[PacketSniffer] Error cargando reglas de captura: {e}", level="WARN")

    @classmethod
    def _ensure_cache(cls) -> None:
        """Garantiza que el cache de reglas no haya caducado."""
        if time.time() - cls._last_cache_time > cls._CACHE_TTL:
            cls.reload_rules()

    @classmethod
    def inspect_packet(
        cls,
        packet: Dict[str, Any],
        from_info: Optional[Any] = None,
        to_info: Optional[Any] = None,
        channels_map: Optional[Dict[int, Any]] = None,
    ) -> bool:
        """Inspecciona un paquete de radio LoRa recibido.

        Si cumple los criterios activos de captura, lo almacena en SQLite y
        emite un evento IPC en tiempo real hacia la interfaz web.

        Devuelve True si el paquete fue capturado, False en caso contrario.
        """
        if not isinstance(packet, dict):
            return False

        cls._ensure_cache()
        if not cls._rules_cache and not cls._captured_nodes_cache:
            return False

        # Deduplicación rápida por ID de paquete
        pkt_id = packet.get("id")
        if pkt_id is not None:
            if pkt_id in cls._recent_packet_ids:
                return False
            cls._recent_packet_ids.append(pkt_id)

        # 1. Extracción de Identidades
        from_num = packet.get("from")
        from_id = packet.get("fromId")
        if not from_id and from_num is not None:
            try:
                from_id = f"!{int(from_num):08x}"
            except Exception:
                from_id = str(from_num)
        from_id_str = str(from_id).strip() if from_id else ""

        to_num = packet.get("to")
        to_id = packet.get("toId")
        if not to_id and to_num is not None:
            try:
                if int(to_num) == 0xFFFFFFFF or int(to_num) == 4294967295:
                    to_id = "^all"
                else:
                    to_id = f"!{int(to_num):08x}"
            except Exception:
                to_id = str(to_num)
        to_id_str = str(to_id).strip() if to_id else ""

        # Si no hay identificadores válidos, no procede
        if not from_id_str and not to_id_str:
            return False

        # 2. Propiedades de Canal y Cifrado
        channel_val = packet.get("channel", 0)
        try:
            channel_int = int(channel_val)
        except Exception:
            channel_int = 0

        decoded = packet.get("decoded")
        is_decoded = isinstance(decoded, dict) and bool(decoded)
        encrypted_field = packet.get("encrypted")
        pki_encrypted = packet.get("pki_encrypted")

        # Cifrado si trae payload cifrado o si no se pudo descifrar
        is_encrypted = bool(encrypted_field or pki_encrypted or not is_decoded)

        # Tráfico Admin Remota / PKI: canal 0 y es un unicast directo (no broadcast ni null)
        is_unicast = bool(to_id_str and to_id_str != "^all" and to_num not in (None, 0, 0xFFFFFFFF, 4294967295))
        is_admin_pki = bool(channel_int == 0 and is_unicast)

        # 3. Evaluación de Reglas de Captura
        matched_rule: Optional[Dict[str, Any]] = None

        for rule in cls._rules_cache:
            r_to = rule.get("to_node_id")
            r_from = rule.get("from_node_id")
            r_chan = rule.get("channel_filter", "all")
            r_enc = bool(rule.get("only_encrypted"))

            # Regla de to / from
            to_matches = (r_to is None) or (r_to.lower() == to_id_str.lower())
            from_matches = (r_from is None) or (r_from.lower() == from_id_str.lower())

            # Al menos uno de los dos debe estar especificado
            if r_to is None and r_from is None:
                continue

            if not (to_matches and from_matches):
                continue

            # Filtro de canal
            if r_chan == "admin_pki":
                if not is_admin_pki:
                    continue
            elif r_chan not in ("all", None, ""):
                try:
                    if int(r_chan) != channel_int:
                        continue
                except ValueError:
                    pass

            # Filtro de cifrado
            if r_enc and not is_encrypted:
                continue

            matched_rule = rule
            break

        # Si no coincidió con ninguna regla explícita, comprobar si alguno de los nodos tiene captura individual
        if not matched_rule:
            if from_id_str in cls._captured_nodes_cache or to_id_str in cls._captured_nodes_cache:
                matched_rule = {
                    "id": None,
                    "save_payload_mode": "full_encrypted",
                    "channel_filter": "all",
                }

        if not matched_rule:
            return False

        # 4. Extracción de Payload y Metadatos de Radio
        save_mode = matched_rule.get("save_payload_mode", "full_encrypted")
        # Si es Admin Remota, se fuerza full_encrypted siempre
        if is_admin_pki:
            save_mode = "full_encrypted"

        payload_bytes: bytes = b""
        payload_text: Optional[str] = None
        portnum_str: Optional[str] = None

        if is_decoded and decoded:
            portnum_str = str(decoded.get("portnum") or "UNKNOWN")
            raw_p = decoded.get("payload")
            if isinstance(raw_p, bytes):
                payload_bytes = raw_p
            elif isinstance(raw_p, str):
                payload_bytes = raw_p.encode("utf-8", errors="replace")

            if "text" in decoded and decoded["text"]:
                payload_text = str(decoded["text"])
        elif encrypted_field:
            portnum_str = "ENCRYPTED"
            if isinstance(encrypted_field, bytes):
                payload_bytes = encrypted_field
            elif isinstance(encrypted_field, str):
                payload_bytes = encrypted_field.encode("utf-8", errors="replace")
        elif pki_encrypted:
            portnum_str = "PKI_ENCRYPTED"
            if isinstance(pki_encrypted, bytes):
                payload_bytes = pki_encrypted
            elif isinstance(pki_encrypted, str):
                payload_bytes = pki_encrypted.encode("utf-8", errors="replace")

        payload_hex = payload_bytes.hex() if payload_bytes else ""
        payload_size = len(payload_bytes)

        # Si el usuario solo quiso guardar texto si está disponible, no guardar BLOB binario
        final_payload_raw = payload_bytes if (save_mode == "full_encrypted" or not payload_text) else None

        # Nombres de nodos
        from_name = getattr(from_info, "name", None) or getattr(from_info, "short_name", None)
        to_name = getattr(to_info, "name", None) or getattr(to_info, "short_name", None)

        # Nombre de canal
        channel_name = None
        if is_admin_pki:
            channel_name = "Admin Remota (PKI)"
        elif channels_map and channel_int in channels_map:
            ch_obj = channels_map[channel_int]
            channel_name = getattr(ch_obj, "name", None) or (ch_obj.get("name") if isinstance(ch_obj, dict) else f"Canal {channel_int}")
        else:
            channel_name = f"Canal {channel_int}"

        # Enrutamiento y saltos
        hop_limit = packet.get("hopLimit")
        hop_start = packet.get("hopStart")
        hops = None
        if hop_start is not None and hop_limit is not None:
            try:
                hl = int(hop_limit)
                hs = int(hop_start)
                if hs >= hl:
                    hops = hs - hl
            except Exception:
                pass

        next_hop = packet.get("nextHop") or packet.get("next_hop")
        relay_node = packet.get("relayNode") or packet.get("relay_node")
        want_ack = bool(packet.get("wantAck") or packet.get("want_ack"))

        rx_time = int(packet.get("rxTime") or time.time())
        created_at_iso = to_utc_iso(rx_time)

        packet_record = {
            "created_at": created_at_iso,
            "packet_id": packet.get("id"),
            "rx_time": rx_time,
            "to_num": int(to_num) if to_num is not None else None,
            "to_id": to_id_str,
            "to_name": to_name,
            "from_num": int(from_num) if from_num is not None else None,
            "from_id": from_id_str,
            "from_name": from_name,
            "channel": channel_int,
            "channel_name": channel_name,
            "is_encrypted": 1 if is_encrypted else 0,
            "is_admin_pki": 1 if is_admin_pki else 0,
            "next_hop": int(next_hop) if next_hop is not None else None,
            "relay_node": int(relay_node) if relay_node is not None else None,
            "want_ack": 1 if want_ack else 0,
            "hop_limit": int(hop_limit) if hop_limit is not None else None,
            "hop_start": int(hop_start) if hop_start is not None else None,
            "hops": hops,
            "rx_snr": packet.get("rxSnr"),
            "rx_rssi": packet.get("rxRssi"),
            "payload_raw": final_payload_raw,
            "payload_hex": payload_hex,
            "payload_text": payload_text,
            "payload_size": payload_size,
            "portnum": portnum_str,
            "rule_id": matched_rule.get("id"),
        }

        # 5. Inserción persistente en SQLite
        try:
            db = Database()
            db_id = db.insert_captured_packet(packet_record)
            packet_record["id"] = db_id
            log_p(
                f"[PacketSniffer] 📷 Paquete #{db_id} capturado: de {from_id_str} a {to_id_str} "
                f"ch={channel_int} enc={is_encrypted} pki={is_admin_pki} bytes={payload_size}",
                level="INFO",
            )
        except Exception as e:
            log_p(f"[PacketSniffer] Error guardando paquete capturado: {e}", level="WARN")
            return False

        # 6. Emisión en tiempo real por IPC a la interfaz web (sin BLOB binario para JSON)
        try:
            from Models.EventBroadcaster import broadcast_event

            ipc_payload = dict(packet_record)
            if "payload_raw" in ipc_payload:
                del ipc_payload["payload_raw"]

            broadcast_event("packet_captured", ipc_payload, ts=created_at_iso)
        except Exception:
            pass

        return True
