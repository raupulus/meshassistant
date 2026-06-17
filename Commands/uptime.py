def uptime_callback(interface, args, msg, metadata):
    print('uptime:')

    # Respuesta mínima (placeholder)
    response = 'Uptime: N/D'
    interface.reply_to_message(response, metadata)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
