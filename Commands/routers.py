from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List
from functions import reply_long, log_p


def _format_time_ago(iso_str: str | None) -> str:
    if not iso_str:
        return 'sin señal'
    try:
        # Si viene como timestamp numérico
        if isinstance(iso_str, (int, float)) or str(iso_str).isdigit():
            dt = datetime.fromtimestamp(float(iso_str))
        else:
            dt = datetime.fromisoformat(str(iso_str))
        diff = datetime.now() - dt
        seconds = int(diff.total_seconds())
        if seconds < 0:
            return 'ahora'
        if seconds < 60:
            return f'hace {seconds}s'
        minutes = seconds // 60
        if minutes < 60:
            return f'hace {minutes}m'
        hours = minutes // 60
        if hours < 24:
            return f'hace {hours}h'
        days = hours // 24
        return f'hace {days}d'
    except Exception:
        return 'sin señal'


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

    try:
        from Models.Database import Database
        db = Database()
        items: List[str] = []

        router_nodes = db.get_router_nodes(routers_cfg)

        for node in router_nodes:
            if node.get('offline'):
                ident = node.get('identifier', 'N/D')
                items.append(f"{ident}: offline")
                continue

            name = node.get('short_name') or node.get('name') or node.get('node_id')
            ts = node.get('last_heard') or node.get('updated_at')
            ago = _format_time_ago(ts)

            details = [ago]
            if node.get('via_mqtt'):
                details.append('MQTT')
            elif node.get('snr') is not None:
                details.append(f"{node['snr']:.1f}dB")

            hops = node.get('hops')
            if hops is not None:
                details.append(f"{hops}h")

            items.append(f"{name}: " + ', '.join(details))

        if not items:
            response = "No hay routers configurados o detectados en la malla."
        else:
            response = "Routers: " + " · ".join(items)

    except Exception as e:
        log_p(f"Error consultando routers: {e}", level="WARN")
        response = f"No se pudo consultar el estado de los routers: {e}"

    reply_long(interface, metadata, response)
