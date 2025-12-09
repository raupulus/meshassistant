def chiste_callback (interface, args, msg, metadata):
    if msg in ['/chiste help', '!chiste help', '/chiste info', '!chiste info',
               '/chiste ayuda', '!chiste ayuda']:

        from data import commands_dict

        command_info = commands_dict.get('chiste', None)

        if command_info:
            response = command_info['info']
        else:
            response = 'Comando no encontrado'

    else:
        response = 'Chiste: Work In Progress'

    interface.reply_to_message(response, metadata)
