def prevision_callback(interface, args, msg, metadata):
    """/prevision — Predicción meteorológica de varios días (municipio).

    Estrategia BD-first con fallback on-demand:
    1. Lee la última previsión multi-día guardada por el cron (scope='forecast').
    2. Si no hay dato o está obsoleto (>12 h), intenta descargarla en vivo de
       AEMET en ese momento (requiere Internet en la Pi).
    3. Si tampoco hay, cae al texto general de provincia disponible en BD.
    """
    from functions import reply_long
    from datetime import datetime, timedelta

    text = None

    # 1) BD: última previsión multi-día
    record = None
    try:
        from Models.Database import Database
        record = Database().aemet_weather_get_latest(scope='forecast')
    except Exception as e:
        print(f"Error leyendo previsión: {e}")

    stale = True
    if record and record.get('content'):
        try:
            created = datetime.fromisoformat(record.get('created_at'))
            stale = (datetime.now() - created) > timedelta(hours=12)
        except Exception:
            stale = True
        if not stale:
            text = record.get('content')

    # 2) Fallback on-demand (en vivo) si no hay dato fresco.
    # Se limita la petición de red a una vez cada ONDEMAND_REFRESH_MIN minutos
    # (def. 10) para no bloquear el hilo de recepción en cada /prevision, y con
    # timeout bajo (4s, 1 intento) porque corre dentro del callback.
    if text is None:
        try:
            import env
            if getattr(env, 'AEMET_API_KEY', None):
                from Models.Database import Database
                db = Database()
                refresh_min = int(getattr(env, 'ONDEMAND_REFRESH_MIN', 10) or 10)
                last = db.get_task_last_run('prevision_ondemand')
                allow_net = True
                if last:
                    try:
                        if datetime.now() - datetime.fromisoformat(last) < timedelta(minutes=refresh_min):
                            allow_net = False
                    except Exception:
                        pass

                if allow_net:
                    from Models.Aemet import Aemet
                    aemet = Aemet(timeout=4.0, retries=1)
                    days = int(getattr(env, 'AEMET_FORECAST_DAYS', 4) or 4)
                    db.set_task_run('prevision_ondemand')  # marca el intento
                    live = aemet.fetch_city_forecast_multi(days=days)
                    if live:
                        text = live
                        # Cachear para próximas consultas offline
                        try:
                            db.aemet_weather_insert(
                                scope='forecast', content=live,
                                province=aemet.province, city=aemet.city,
                                city_code=aemet.resolve_city_code(), day='multi', data_raw=live,
                            )
                        except Exception:
                            pass
        except Exception as e:
            print(f"Error previsión on-demand: {e}")

    # 3) Último recurso: texto guardado de provincia/municipio (el de /weather)
    if text is None and record and record.get('content'):
        text = record.get('content')
    if text is None:
        try:
            from Models.Database import Database
            alt = Database().aemet_weather_get_latest()
            if alt and alt.get('content'):
                text = alt.get('content')
        except Exception:
            pass

    if not text:
        interface.reply_to_message('Sin previsión disponible todavía. Inténtalo más tarde.', metadata)
        return

    reply_long(interface, metadata, f'Previsión: {text}')
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
