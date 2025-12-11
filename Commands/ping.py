import json


def ping_callback(interface, args, msg, metadata):
    print(f'Pong a "{metadata.get("node_from").get("name")}", MQTT: {metadata.get("node_from").get("via_mqtt")}')

    # Guardar ping en la base de datos
    try:
        from Models.Database import Database

        node_from = (metadata or {}).get('node_from') or {}
        node_to = (metadata or {}).get('node_to') or {}

        from_id = node_from.get('id')
        from_name = node_from.get('name') or node_from.get('short_name')
        to_id = node_to.get('id') or '^all'
        hops = node_from.get('hops')

        # Serializar datos crudos relevantes
        raw = {
            'msg': msg,
            'args': args,
            'metadata': {
                'node_from': {
                    'id': from_id,
                    'name': from_name,
                    'snr': node_from.get('snr'),
                    'rssi': node_from.get('rssi'),
                    'hops': hops,
                    'via_mqtt': node_from.get('via_mqtt'),
                },
                'node_to': node_to,
                'channel': metadata.get('channel'),
                'is_direct': metadata.get('is_direct'),
            }
        }
        data_raw = json.dumps(raw, ensure_ascii=False)

        db = Database()
        db.save_ping(from_id=from_id, to_id=to_id, from_name=from_name, hops=hops, data_raw=data_raw)
    except Exception as e:
        # No interrumpir la respuesta por errores de BD
        print(f"Error guardando ping: {e}")

    # Responder como hasta ahora
    if metadata.get("node_from").get('via_mqtt'):
        response = 'Pong, via MQTT'
        interface.reply_to_message(response, metadata)
    else:
        hops = metadata.get('node_from').get('hops')

        if hops is not None:
            response = f'Pong desde Chipiona, {hops} hops'
            interface.reply_to_message(response, metadata)
