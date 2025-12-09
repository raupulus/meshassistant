def about_callback(interface, args, msg, metadata):
    print('Información sobre el proyecto')

    response = ('Proyecto para bot cliente meshtastic creado por '
                'https://raupulus.dev a modo de asistente offline. Envía '
                '!help para ayuda')

    interface.reply_to_message(response, metadata)
