
def help_callback(interface, args, msg, metadata):
    from data import commands_dict
    from functions import split_messages, MESH_MAX_LEN, MESH_MAX_PARTS
    from time import sleep

    if args and len(args):
        # Ayuda concreta de un comando: !help <comando>
        name = args[0].lstrip('/!').lower()
        command_info = commands_dict.get(name)
        if command_info:
            response = f"/{name}: {command_info['info']}"
        else:
            response = 'Comando no encontrado. Envía /help para la lista.'
        interface.reply_to_message(response, metadata)
        return

    # Lista completa de comandos, generada dinámicamente desde commands_dict.
    # Se omiten los marcados como "hidden" (alias) para no duplicar la lista.
    cmds = ' '.join(f"/{name}" for name, info in commands_dict.items() if not info.get('hidden'))
    full = f"Comandos: {cmds}. Detalle: !help <comando>"

    parts = split_messages(full, max_len=MESH_MAX_LEN, max_parts=MESH_MAX_PARTS)
    for idx, part in enumerate(parts):
        interface.reply_to_message(part, metadata)
        if idx < len(parts) - 1:
            sleep(5)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
