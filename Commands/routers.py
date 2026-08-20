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
    max_hops = int(getattr(env, 'ROUTER_MAX_HOPS', 2) or 2)

    try:
        from Models.Database import Database
        db = Database()
        items: List[str] = []

        router_nodes = db.get_router_nodes(routers_cfg, max_hops=max_hops)

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

            raw_hops = node.get('hops')

            # Si el nodo supera los saltos máximos configurados (ROUTER_MAX_HOPS), se ignora
            if raw_hops is not None and raw_hops > max_hops:
                continue

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
            effective_hops = raw_hops
            is_base = (
                (base_short and short_name and short_name.upper() == str(base_short).upper())
                or (base_id and node_id and node_id.upper() == str(base_id).upper())
            )
            is_direct = (raw_hops == 0) or is_base

            if raw_hops is not None and raw_hops > 0 and (base_short or base_id):
                effective_hops = max(0, raw_hops - 1)

            base_idents = [b for b in [base_short, base_id] if b]
            trace_info = db.get_latest_trace_route_info(node_id or short_name or ident, base_idents)

            # Priorizar información del trace reciente (hops y SNRs exteriores tramo a tramo)
            if trace_info is not None:
                effective_hops = trace_info.get('hops')
                snr_str = trace_info.get('snr_text')
            elif is_direct:
                # Si es directo con nuestro bot o es la base, el SNR registrado es directo y real
                snr_val = node.get('snr')
                snr_str = f"{snr_val:.1f}dB" if snr_val is not None else None
            else:
                # Si es repetido y NO tenemos trace, NO usamos node['snr'] (es el SNR local de la base)
                snr_str = None

            # Si el trace o nodo indica más saltos que max_hops, descartar si no es configurado
            if max_hops is not None and effective_hops is not None and effective_hops > max_hops and not is_configured:
                continue

            if node.get('via_mqtt'):
                items.append(f"[{name}: {ago} - MQTT]")
            elif snr_str:
                if effective_hops is not None:
                    hop_txt = "1 hop" if effective_hops == 1 else f"{effective_hops} hops"
                    items.append(f"[{name}: {ago} - {hop_txt}({snr_str})]")
                else:
                    items.append(f"[{name}: {ago} ({snr_str})]")
            elif effective_hops is not None:
                hop_txt = "1 hop" if effective_hops == 1 else f"{effective_hops} hops"
                items.append(f"[{name}: {ago} - {hop_txt}]")
            else:
                items.append(f"[{name}: {ago}]")

        if not items:
            response = f"No hay routers activos a <= {max_hops} hops detectados en las últimas 24h."
        else:
            response = "Routers: " + ", ".join(items)

    except Exception as e:
        log_p(f"Error consultando routers: {e}", level="WARN")
        response = f"No se pudo consultar el estado de los routers: {e}"

    routers_max_parts = int(getattr(env, 'ROUTERS_MAX_PARTS', 5) or 5)
    reply_long(interface, metadata, response, max_parts=routers_max_parts)
