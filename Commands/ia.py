def ia_callback(interface, args, msg, metadata):
    print('IA')

    # (Respuesta placeholder de IA mínima)
    response = 'IA: funcionalidad en desarrollo'
    interface.reply_to_message(response, metadata)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
