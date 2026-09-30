from functions import log_p
import json


def is_repeated_by_base(metadata: dict, base_id=None, base_short=None, interface=None) -> bool:
    """Verifica fehacientemente si el repetidor inmediato (relay_node) coincide con el nodo base.

    Meshtastic envía en relay_node el byte inferior (1 byte hash: num & 0xFF) o el nodeNum
    del último nodo que retransmitió la trama por radio.
    """
    relay_node = metadata.get("relay_node")
    if relay_node is None:
        node_from = metadata.get("node_from")
        if isinstance(node_from, dict):
            relay_node = node_from.get("relay_node")

    if relay_node is None:
        return False

    base_nums = set()
    base_hashes = set()

    # 1. Desde base_id configurado (ej: '!875e3787' o '875e3787')
    if base_id:
        try:
            num = int(str(base_id).lstrip('!'), 16)
            base_nums.add(num)
            base_hashes.add(num & 0xFF)
        except Exception:
            pass

    # 2. Desde los nodos cargados en la interfaz si coinciden por short_name o ID
    if interface and hasattr(interface, 'node_dict'):
        for nid, n in (interface.node_dict or {}).items():
            s_name = getattr(n, 'short_name', '') or ''
            if (base_short and s_name.upper() == str(base_short).upper()) or (base_id and nid == base_id):
                n_num = getattr(n, 'num', None)
                if n_num is not None:
                    try:
                        n_num_int = int(n_num)
                        base_nums.add(n_num_int)
                        base_hashes.add(n_num_int & 0xFF)
                    except Exception:
                        pass

    # 3. Fallback a BD si la interfaz no tenía el nodo en RAM
    if not base_nums and (base_id or base_short):
        try:
            from Models.Database import Database
            db = Database()
            if base_id:
                n = db.get_node(str(base_id))
                if n and n.get('num'):
                    n_num_int = int(n['num'])
                    base_nums.add(n_num_int)
                    base_hashes.add(n_num_int & 0xFF)
            if base_short and not base_nums:
                n = db.get_node_by_short_name(str(base_short))
                if n and n.get('num'):
                    n_num_int = int(n['num'])
                    base_nums.add(n_num_int)
                    base_hashes.add(n_num_int & 0xFF)
        except Exception:
            pass

    try:
        r_int = int(relay_node)
        return (r_int in base_nums) or (r_int in base_hashes)
    except Exception:
        return False


def ping_callback(interface, args, msg, metadata):
    metadata = metadata or {}
    node_from = metadata.get("node_from") if isinstance(metadata.get("node_from"), dict) else {}
    node_to = metadata.get("node_to") if isinstance(metadata.get("node_to"), dict) else {}

    from_id = node_from.get('id') or (metadata.get('node_from') if isinstance(metadata.get('node_from'), str) else None)
    from_name = node_from.get('name') or node_from.get('short_name')
    to_id = node_to.get('id') or (metadata.get('node_to') if isinstance(metadata.get('node_to'), str) else '^all')
    raw_hops = node_from.get('hops') if isinstance(node_from, dict) else metadata.get('hops')
    via_mqtt = bool(node_from.get('via_mqtt', False) if isinstance(node_from, dict) else metadata.get('via_mqtt', False))

    import env
    base_short = getattr(env, 'BASE_NODE_SHORT_NAME', None) or getattr(env, 'MESH_GATEWAY_SHORT_NAME', 'RAU0') or 'RAU0'
    base_id = getattr(env, 'BASE_NODE_ID', None)

    # Calcular saltos efectivos respecto al nodo base:
    # Solo descontamos 1 salto si el paquete vino repetido (raw_hops > 0) Y hemos verificado
    # fehacientemente que el repetidor inmediato (relay_node) coincide con nuestro nodo base.
    repeated_by_base = False
    effective_hops = raw_hops
    if raw_hops is not None and raw_hops > 0 and (base_short or base_id):
        repeated_by_base = is_repeated_by_base(metadata, base_id=base_id, base_short=base_short, interface=interface)
        if repeated_by_base:
            effective_hops = max(0, raw_hops - 1)

    log_p(f'Pong a "{from_name or from_id or "desconocido"}", MQTT: {via_mqtt}, raw_hops: {raw_hops}, eff_hops: {effective_hops}, rep_by_base: {repeated_by_base}')

    # Guardar ping en la base de datos
    try:
        from Models.Database import Database

        # Serializar datos crudos relevantes
        raw = {
            'msg': msg,
            'args': args,
            'metadata': {
                'node_from': {
                    'id': from_id,
                    'name': from_name,
                    'snr': node_from.get('snr') if isinstance(node_from, dict) else metadata.get('rx_snr'),
                    'rssi': node_from.get('rssi') if isinstance(node_from, dict) else metadata.get('rx_rssi'),
                    'hops': effective_hops,
                    'raw_hops': raw_hops,
                    'repeated_by_base': repeated_by_base,
                    'relay_node': metadata.get('relay_node'),
                    'via_mqtt': via_mqtt,
                },
                'node_to': node_to,
                'channel': metadata.get('channel'),
                'is_direct': metadata.get('is_direct'),
            }
        }
        data_raw = json.dumps(raw, ensure_ascii=False)

        db = Database()
        db.save_ping(from_id=from_id, to_id=to_id, from_name=from_name, hops=effective_hops, data_raw=data_raw)
    except Exception as e:
        # No interrumpir la respuesta por errores de BD
        log_p(f"Error guardando ping: {e}", level="WARN")

    # Responder al ping
    if via_mqtt:
        response = 'Pong, via MQTT'
    else:
        # Enlace directo al bot (0 saltos de radio): mostramos SNR medido
        if raw_hops == 0:
            snr = node_from.get('snr') if isinstance(node_from, dict) else metadata.get('rx_snr')
            if snr is not None:
                response = f'Pong desde Chipiona (SNR: {snr:+.1f} dB)'
            else:
                response = 'Pong desde Chipiona'
        elif raw_hops is not None and raw_hops > 0:
            hops_txt = 'hop' if effective_hops == 1 else 'hops'
            response = f'Pong desde Chipiona, {effective_hops} {hops_txt}'
        else:
            response = 'Pong desde Chipiona'

    interface.reply_to_message(response, metadata)

    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.

