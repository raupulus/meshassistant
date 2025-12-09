
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

