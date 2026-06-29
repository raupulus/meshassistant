def uptime_callback(interface, args, msg, metadata):
    from functions import format_uptime

    response = f'Encendido desde hace {format_uptime()}'
    interface.reply_to_message(response, metadata)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
