def luna_callback(interface, args, msg, metadata):
    """/luna — Fase lunar actual e iluminación, con próxima llena/nueva.

    Cálculo 100% offline (edad lunar respecto al mes sinódico). Útil para pesca
    y observación. No requiere Internet.
    """
    try:
        from Models.Astro import moon_phase, next_phase_dates

        ph = moon_phase()
        nxt = next_phase_dates()

        nombre = ph.get('phase_name', 'Luna')
        ilum = int(round(ph.get('illumination', 0) * 100))

        new_m = nxt.get('next_new')
        full_m = nxt.get('next_full')

        # La tendencia solo aporta en fases intermedias (en llena/nueva sobra).
        if nombre in ('Luna llena', 'Luna nueva'):
            response = f'Luna: {nombre}, {ilum}% iluminada.'
        else:
            tendencia = 'creciente' if ph.get('waxing') else 'menguante'
            response = f'Luna: {nombre}, {ilum}% iluminada ({tendencia}).'
        if full_m and new_m:
            response += f' Llena: {full_m.strftime("%d/%m")}. Nueva: {new_m.strftime("%d/%m")}.'
    except Exception as e:
        response = f'No se pudo calcular la luna: {e}'

    interface.reply_to_message(response, metadata)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
