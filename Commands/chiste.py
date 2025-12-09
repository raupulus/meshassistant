def chiste_callback(interface, args, msg, metadata):
    # Ayuda/Info del comando
    if msg in ['/chiste help', '!chiste help', '/chiste info', '!chiste info',
               '/chiste ayuda', '!chiste ayuda']:

        from data import commands_dict

        command_info = commands_dict.get('chiste', None)

        if command_info:
            response = command_info['info']
        else:
            response = 'Comando no encontrado'
        interface.reply_to_message(response, metadata)
        return

    # Añadir chiste: "/chiste add ..." o "!chiste add ..."
    if msg.startswith('/chiste add') or msg.startswith('!chiste add') or (args and args[0] == 'add'):
        # Extraer contenido tras la palabra 'add'
        try:
            content = msg.split('add', 1)[1].strip()
        except Exception:
            content = ''

        if not content:
            interface.reply_to_message('Uso: !chiste add Tu chiste aquí', metadata)
            return

        # Determinar origen del chiste
        node_from = (metadata or {}).get('node_from') or {}
        from_name = node_from.get('short_name') or node_from.get('name') or 'desconocido'

        # Guardar en BD con need_upload=true y need_approve=true
        try:
            from Models.Database import Database
            db = Database()
            db.save_chiste(from_=from_name, content=content, need_upload=True, need_approve=True)
            interface.reply_to_message('✅ Chiste recibido. Queda pendiente de aprobación. ¡Gracias!', metadata)
        except Exception as e:
            interface.reply_to_message(f'❌ Error guardando el chiste: {e}', metadata)
        return

    # Obtener chiste aleatorio aprobado
    try:
        from Models.Database import Database
        db = Database()
        chiste = db.get_random_chiste(approved_only=True)
        if chiste and chiste.get('content'):
            response = f"Chiste: {chiste.get('content')}"
        else:
            response = 'No hay chistes aprobados aún. ¡Añade uno con: !chiste add Tu chiste!'
    except Exception as e:
        response = f'Error al obtener chistes: {e}'

    interface.reply_to_message(response, metadata)
