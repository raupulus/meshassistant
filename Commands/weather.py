def _split_messages(text, max_len=200, max_parts=2):
    """Trocea un texto en como mucho `max_parts` mensajes de `max_len` caracteres.

    Intenta cortar en un límite de palabra para no partir términos. Si el texto
    excede la capacidad total, el último mensaje termina en '…'.
    """
    text = (text or '').strip()
    if not text:
        return []

    messages = []
    remaining = text
    for i in range(max_parts):
        if not remaining:
            break
        last = (i == max_parts - 1)

        if len(remaining) <= max_len:
            messages.append(remaining)
            remaining = ''
            break

        # Reservar un carácter para el indicador de truncado en el último tramo
        cap = max_len - 1 if last else max_len
        cut = remaining[:cap]
        # Cortar en el último espacio para no partir palabras
        sp = cut.rfind(' ')
        if sp > int(cap * 0.6):
            cut = cut[:sp]
        cut = cut.rstrip()

        if last:
            messages.append((cut + '…').strip())
            remaining = ''
        else:
            messages.append(cut)
            remaining = remaining[len(cut):].lstrip()

    return messages


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

    # Trocear en 1-2 mensajes de ~200 caracteres (límite de Meshtastic)
    parts = _split_messages(full, max_len=200, max_parts=2)
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
