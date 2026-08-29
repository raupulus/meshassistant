def marea_callback(interface, args, msg, metadata):
    """/marea — Pleamares y bajamares del día o estado de la mar costera.

    - Sin argumentos: pleamares y bajamares del día actual con horarios y alturas.
    - /marea mar | costa: boletín marítimo costero oficial de Cádiz (viento Beaufort, oleaje, visibilidad).
    """
    from functions import reply_long, log_p
    from datetime import datetime, timedelta
    from Models.Database import Database

    db = Database()

    # 1) Caso: /marea mar | /marea costa
    if args and args[0].lower() in ('mar', 'costa', 'oleaje', 'viento'):
        rec_m = db.aemet_maritime_get_latest()
        if rec_m and rec_m.get('summary'):
            reply_long(interface, metadata, rec_m.get('summary'))
            return
        # Intento on-demand si no hay en BD
        try:
            from Models.Aemet import Aemet
            aemet = Aemet()
            costa_code = getattr(aemet, 'maritime_coast_code', '42')
            mar_data = aemet.fetch_maritime_coastal(costa_code=costa_code)
            if mar_data:
                summary_mar = aemet.format_maritime_coastal(mar_data)
                if summary_mar:
                    db.aemet_maritime_insert(
                        costa_code=costa_code,
                        costa_name="Costa Andalucía Occidental / Cádiz",
                        data_json=mar_data,
                        summary=summary_mar,
                    )
                    reply_long(interface, metadata, summary_mar)
                    return
        except Exception as e:
            log_p(f"Error consultando boletín costero on-demand: {e}", level="WARN")

        interface.reply_to_message("🌊 Sin boletín costero disponible en este momento.", metadata)
        return

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
