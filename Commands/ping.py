from functions import log_p
import json


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

    # Calcular saltos efectivos respecto al nodo base/azotea
    # Si el paquete vino repetido (hops > 0) y tenemos nodo base configurado,
    # restamos 1 salto para reflejar los saltos reales hacia la azotea.
    # Si vino directo al bot (raw_hops == 0), no se descuenta nada.
    effective_hops = raw_hops
    if raw_hops is not None and raw_hops > 0 and (base_short or base_id):
        effective_hops = max(0, raw_hops - 1)

    log_p(f'Pong a "{from_name or from_id or "desconocido"}", MQTT: {via_mqtt}, raw_hops: {raw_hops}, eff_hops: {effective_hops}')

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
            # Enlace repetido: mostramos los saltos efectivos sin SNR (para no mostrar SNR del enlace local)
            hops_txt = 'hop' if effective_hops == 1 else 'hops'
            response = f'Pong desde Chipiona, {effective_hops} {hops_txt}'
        else:
            response = 'Pong desde Chipiona'

    interface.reply_to_message(response, metadata)

    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.

