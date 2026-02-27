
def help_callback(interface, args, msg, metadata):
    if not args or not len(args):
        response = ('Comandos: /help,/ping,/about,/weather,/chiste,/uptime. '
                    'Envía !help comando para más info')
    else:
        from data import commands_dict

        command_info = commands_dict.get(args[0], None)

        if command_info:
            response = command_info['info']
        else:
            response = 'Comando no encontrado'

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
                cmd = 'help'
        # Almacenar argumentos como mensaje posterior
        message_tail = ' '.join(args) if args else None
        Database().log_command(node_id=node_id, command=cmd or 'help', message=message_tail, parameters=None)
    except Exception:
        pass

