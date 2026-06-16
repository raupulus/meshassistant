def weather_callback(interface, args, msg, metadata):
    print('weather')

    response = 'Tiempo real: ???; Predicción: ???'

    interface.reply_to_message(response, metadata)

    # Registrar comando en histórico (commands_sent)
    try:
        from Models.Database import Database
        node_from = (metadata or {}).get('node_from') or {}
        node_id = node_from.get('id')
        cmd = None
        if isinstance(msg, str) and (msg.startswith('/') or msg.startswith('!')):
            try:
                cmd = msg.split()[0][1:].lower()
            except Exception:
                cmd = 'weather'
        message_tail = ' '.join(args) if args else None
        Database().log_command(node_id=node_id, command=cmd or 'weather', message=message_tail, parameters=None)
    except Exception:
        pass
