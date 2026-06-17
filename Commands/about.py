def about_callback(interface, args, msg, metadata):
    print('Información sobre el proyecto')

    response = ('Proyecto para bot cliente meshtastic creado por '
                'https://raupulus.dev a modo de asistente offline. Envía '
                '!help para ayuda')

    interface.reply_to_message(response, metadata)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
