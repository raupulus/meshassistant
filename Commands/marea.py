def marea_callback(interface, args, msg, metadata):
    """/marea — Próximas pleamares y bajamares de la zona (por defecto Chipiona).

    Estrategia BD-first con fallback on-demand:
    1. Lee la última predicción guardada por el cron de mareas (offline).
    2. Si no hay dato fresco o quedan menos de 2 extremos futuros, calcula en
       vivo (WorldTides/Open-Meteo si hay Internet; si no, estimación lunar).
    Las estimaciones offline se marcan con '~' por ser aproximadas.
    """
    from functions import reply_long
    from datetime import datetime, timedelta

    def _parse(extremes):
        out = []
        for e in extremes or []:
            t = e.get('time')
            try:
                dt = datetime.fromisoformat(t) if isinstance(t, str) else t
            except Exception:
                continue
            out.append({'time': dt, 'type': e.get('type'), 'height': e.get('height')})
        return out

    source = None
    approximate = False
    name = 'la zona'
    extremes = []

    # 1) BD
    try:
        from Models.Database import Database
        latest = Database().tides_get_latest()
    except Exception:
        latest = None

    if latest:
        extremes = _parse(latest.get('extremes'))
        source = latest.get('source')
        approximate = bool(latest.get('approximate'))
        name = latest.get('location') or name

    # ¿Hay suficientes extremos futuros?
    try:
        from Models.Tides import next_extremes, compute_tides
        tz = extremes[0]['time'].tzinfo if extremes else None
        now = datetime.now(tz) if tz else datetime.now()
        upcoming = next_extremes(extremes, now=now, count=4)
    except Exception:
        upcoming = []

    # 2) Fallback on-demand (vivo o estimación).
    # Para no bloquear el hilo de recepción en cada petición, la consulta de red
    # se limita a una vez cada ONDEMAND_REFRESH_MIN minutos (def. 10): si se
    # intentó hace poco, se calcula offline (estimación) sin tocar la red.
    if len(upcoming) < 2:
        try:
            from Models.Tides import compute_tides, next_extremes
            from Models.Database import Database
            import env
            refresh_min = int(getattr(env, 'ONDEMAND_REFRESH_MIN', 10) or 10)

            db = Database()
            last = db.get_task_last_run('marea_ondemand')
            allow_net = True
            if last:
                try:
                    if datetime.now() - datetime.fromisoformat(last) < timedelta(minutes=refresh_min):
                        allow_net = False
                except Exception:
                    pass

            # timeout bajo (4s): se ejecuta dentro del callback de recepción
            result = compute_tides(days=2, allow_network=allow_net, timeout=4.0)
            if allow_net:
                db.set_task_run('marea_ondemand')  # marca el intento (éxito o no)

            extremes = result.get('extremes') or []
            source = result.get('source')
            approximate = bool(result.get('approximate'))
            name = result.get('name') or name
            upcoming = next_extremes(extremes, count=4)
            # Cachear si es fuente real
            if extremes and not approximate:
                try:
                    db.tides_insert(location=name, source=source,
                                    approximate=False, extremes=extremes)
                except Exception:
                    pass
        except Exception as e:
            interface.reply_to_message(f'No se pudo calcular la marea: {e}', metadata)
            return

    if not upcoming:
        interface.reply_to_message('Sin datos de marea disponibles.', metadata)
        return

    etiquetas = {'high': 'Pleamar', 'low': 'Bajamar'}
    trozos = []
    for e in upcoming:
        hhmm = e['time'].strftime('%H:%M')
        et = etiquetas.get(e.get('type'), '?')
        h = e.get('height')
        if h is not None:
            trozos.append(f'{et} {hhmm} ({h:.1f}m)')
        else:
            trozos.append(f'{et} {hhmm}')

    prefijo = f'Marea {name}'
    if approximate:
        prefijo += ' (~estimada)'
    response = f'{prefijo}: ' + ', '.join(trozos) + '.'

    reply_long(interface, metadata, response)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
