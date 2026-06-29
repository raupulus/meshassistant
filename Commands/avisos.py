def avisos_callback(interface, args, msg, metadata):
    """/avisos — Últimos avisos meteorológicos de AEMET para la provincia.

    Lee de la BD las alertas descargadas por el cron de AEMET (offline). No hace
    peticiones en vivo: muestra lo que ya se ha recibido en las últimas 48 h.
    """
    from functions import reply_long

    try:
        from Models.Database import Database
        alerts = Database().aemet_get_recent_alerts(limit=3, hours=48)
    except Exception as e:
        interface.reply_to_message(f'No se pudieron consultar los avisos: {e}', metadata)
        return

    if not alerts:
        interface.reply_to_message('Sin avisos AEMET recientes para la provincia.', metadata)
        return

    # Mostrar el aviso más reciente con detalle; si hay más, indicarlo.
    main = alerts[0]
    body = (main.get('message') or main.get('data_raw') or '').strip()
    extra = len(alerts) - 1

    texto = f'Aviso AEMET: {body}'
    if extra > 0:
        texto += f' (+{extra} aviso(s) más reciente(s))'

    reply_long(interface, metadata, texto)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
