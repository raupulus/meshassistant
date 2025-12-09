def ping_callback(interface, args, msg, metadata):
    print(f'Pong a "{metadata.get("node_from").get("name")}", MQTT: {metadata.get("node_from").get("via_mqtt")}')

    #print('metadata:', metadata)

    if metadata.get("node_from").get('via_mqtt'):
        response = f'Pong, via MQTT'
        interface.reply_to_message(response, metadata)
    else:
        hops = metadata.get('node_from').get('hops')

        if not hops is None:
            response = f'Pong, {hops} hops'
            interface.reply_to_message(response, metadata)
