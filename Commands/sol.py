def sol_callback(interface, args, msg, metadata):
    """/sol — Orto (amanecer), ocaso (atardecer) y duración del día.

    Cálculo 100% offline (algoritmo solar NOAA) para la ubicación configurada
    (por defecto Chipiona). No requiere Internet.
    """
    try:
        from Models.Astro import sun_info

        info = sun_info()
        name = info.get('name', 'tu zona')
        sr = info.get('sunrise')
        ss = info.get('sunset')
        length = info.get('day_length')

        if not sr or not ss:
            response = f'Sol {name}: hoy no hay orto/ocaso normal (latitud extrema).'
        else:
            partes = [f'Sol {name}: orto {sr.strftime("%H:%M")}', f'ocaso {ss.strftime("%H:%M")}']
            if length:
                total = int(length.total_seconds())
                h, m = total // 3600, (total % 3600) // 60
                partes.append(f'día {h}h{m:02d}m')
            response = ', '.join(partes) + '.'
    except Exception as e:
        response = f'No se pudo calcular el sol: {e}'

    interface.reply_to_message(response, metadata)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
