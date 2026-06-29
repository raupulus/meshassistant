def weather_callback(interface, args, msg, metadata):
    print('weather')

    # Leer la última predicción descargada (histórico en aemet_weather)
    record = None
    try:
        from Models.Database import Database
        record = Database().aemet_weather_get_latest()
    except Exception as e:
        print(f"Error leyendo clima: {e}")

    if not record or not record.get('content'):
        interface.reply_to_message(
            'Sin datos de clima disponibles todavía. Inténtalo más tarde.',
            metadata,
        )
        return

    scope = record.get('scope')
    if scope == 'province':
        label = record.get('province') or 'provincia'
    else:
        label = record.get('city') or 'tu zona'

    body = record.get('content') or ''
    full = f"Tiempo {label}: {body}"

    # Trocear en hasta 3 mensajes de ~200 caracteres (límite de Meshtastic)
    from functions import split_messages, MESH_MAX_LEN, MESH_MAX_PARTS
    parts = split_messages(full, max_len=MESH_MAX_LEN, max_parts=MESH_MAX_PARTS)
    if not parts:
        interface.reply_to_message('Sin datos de clima disponibles.', metadata)
        return

    from time import sleep
    for idx, part in enumerate(parts):
        interface.reply_to_message(part, metadata)
        # Pequeña espera entre partes para no saturar la malla
        if idx < len(parts) - 1:
            sleep(5)

    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
