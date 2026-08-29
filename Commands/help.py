
def help_callback(interface, args, msg, metadata):
    """/help — Lista de comandos y ayuda detallada."""
    from data import commands_dict
    from functions import split_messages, MESH_MAX_BYTES, MESH_MAX_PARTS, reply_long
    from time import sleep

    if args and len(args):
        # Ayuda concreta de un comando: /help <comando>
        name = args[0].lstrip('/!').lower()
        command_info = commands_dict.get(name)
        if command_info:
            usage = command_info.get('usage', f"/{name}")
            info = command_info.get('info', '')
            response = f"📖 /{name}\n• Descripción: {info}\n• Uso: {usage}"
        else:
            response = '❌ Comando no encontrado. Envía /help para ver la lista de comandos disponibles.'
        reply_long(interface, metadata, response)
        return

    # Lista completa de comandos principales (sin alias ocultos)
    cmds = [f"/{name}" for name, info in commands_dict.items() if not info.get('hidden')]
    full = f"🤖 Comandos disponibles: {', '.join(cmds)}.\n💡 Usa /help <comando> para ver opciones y ejemplos."

    reply_long(interface, metadata, full)

