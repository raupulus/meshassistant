from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List
from functions import reply_long, log_p


def _get_time_diff_seconds(iso_str: str | None) -> int | None:
    if not iso_str:
        return None
    try:
        if isinstance(iso_str, (int, float)) or str(iso_str).isdigit():
            dt = datetime.fromtimestamp(float(iso_str))
        else:
            dt = datetime.fromisoformat(str(iso_str))
        diff = datetime.now() - dt
        return max(0, int(diff.total_seconds()))
    except Exception:
        return None


def _format_time_ago(iso_str: str | None) -> str:
    seconds = _get_time_diff_seconds(iso_str)
    if seconds is None:
        return 'sin señal'
    if seconds < 60:
        return f'{seconds}s'
    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes}m'
    hours = minutes // 60
    if hours < 24:
        return f'{hours}h'
    days = hours // 24
    return f'{days}d'


def routers_callback(interface, args, msg, metadata):
    """/routers — Estado de los routers y repetidores clave de la malla."""
    log_p('Comando /routers recibido')

    import env
    routers_cfg = getattr(env, 'ROUTER_NODES', None) or getattr(env, 'ROUTERS_LIST', None)
    if not routers_cfg:
        gw = getattr(env, 'MESH_GATEWAY_SHORT_NAME', 'RAU0') or 'RAU0'
        routers_cfg = [gw]

    if isinstance(routers_cfg, str):
        routers_cfg = [r.strip() for r in routers_cfg.split(',') if r.strip()]

    configured_set = {str(r).upper() for r in routers_cfg}

    base_short = getattr(env, 'BASE_NODE_SHORT_NAME', None) or getattr(env, 'MESH_GATEWAY_SHORT_NAME', 'RAU0') or 'RAU0'
    base_id = getattr(env, 'BASE_NODE_ID', None)

    try:
        from Models.Database import Database
        db = Database()
        items: List[str] = []

        router_nodes = db.get_router_nodes(routers_cfg)

        for node in router_nodes:
            ident = node.get('identifier')
            short_name = node.get('short_name')
            node_id = node.get('node_id')
            name = short_name or node.get('name') or node_id or ident or 'N/D'

            is_configured = (
                (ident and str(ident).upper() in configured_set)
                or (short_name and str(short_name).upper() in configured_set)
                or (node_id and str(node_id).upper() in configured_set)
            )

            ts = node.get('last_heard') or node.get('updated_at')
            diff_sec = _get_time_diff_seconds(ts)

            # Si no ha sido detectado en 24h (86400s) o no tiene registro, marcar offline
            if node.get('offline') or diff_sec is None or diff_sec >= 86400:
                if is_configured:
                    items.append(f"[{name} | offline]")
                # Nodos auto-detectados no escuchados en 24h se omiten para no saturar
                continue

            ago = _format_time_ago(ts)

            # Descontar 1 salto si vino repetido a través del nodo base
            raw_hops = node.get('hops')
            effective_hops = raw_hops
            if raw_hops is not None and raw_hops > 0 and (base_short or base_id):
                effective_hops = max(0, raw_hops - 1)

            if node.get('via_mqtt'):
                items.append(f"[{name}: {ago} - MQTT]")
            elif node.get('snr') is not None:
                snr_val = node['snr']
                if effective_hops is not None:
                    hop_txt = "1 hop" if effective_hops == 1 else f"{effective_hops} hops"
                    items.append(f"[{name}: {ago} - {hop_txt}({snr_val:.1f}dB)]")
                else:
                    items.append(f"[{name}: {ago} ({snr_val:.1f}dB)]")
            elif effective_hops is not None:
                hop_txt = "1 hop" if effective_hops == 1 else f"{effective_hops} hops"
                items.append(f"[{name}: {ago} - {hop_txt}]")
            else:
                items.append(f"[{name}: {ago}]")

        if not items:
            response = "No hay routers activos detectados en las últimas 24h."
        else:
            response = "Routers: " + ", ".join(items)

    except Exception as e:
        log_p(f"Error consultando routers: {e}", level="WARN")
        response = f"No se pudo consultar el estado de los routers: {e}"

    reply_long(interface, metadata, response)
