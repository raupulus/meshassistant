from functions import log_p, reply_long


def weather_callback(interface, args, msg, metadata):
    """/tiempo /weather — Predicción meteorológica completa para el día actual.

    - Sin argumentos: pronóstico oficial del día actual para la provincia / municipio.
    - /tiempo real | ahora | estacion: última medición física registrada por estación meteorológica.
    - /tiempo <provincia>: pronóstico para otra provincia andaluza (ej. Sevilla, Málaga).
    """
    log_p('Comando /weather recibido')
    
    from Models.Database import Database
    from datetime import datetime, timedelta
    from Models.Aemet import PROV_NAME_TO_CODE, _normalize_name, Aemet

    db = Database()
    aemet = Aemet()

    # 1) Caso: /tiempo real | /tiempo estacion
    if args and args[0].lower() in ('real', 'ahora', 'estacion', 'estación'):
        rec_obs = db.aemet_observation_get_latest()
        if rec_obs and rec_obs.get('summary'):
            reply_long(interface, metadata, rec_obs.get('summary'))
            return
        # Intento on-demand si no hay en BD
        try:
            station_id = getattr(aemet, 'observation_station', '5972X')
            obs_data = aemet.fetch_station_observation(station_id=station_id)
            if obs_data:
                summary_obs = aemet.format_station_observation(obs_data)
                if summary_obs:
                    db.aemet_observation_insert(
                        station_id=station_id,
                        station_name="Cádiz/Costa",
                        data_json=obs_data,
                        summary=summary_obs,
                    )
                    reply_long(interface, metadata, summary_obs)
                    return
        except Exception as e:
            log_p(f"Error consulta estación meteorológica: {e}", level="WARN")

        interface.reply_to_message("🌡️ Sin datos recientes de estación meteorológica.", metadata)
        return

    # 2) Caso: Provincia solicitada o por defecto
    requested_province_code = None
    requested_province_name = None

    if args:
        requested = ' '.join(args)
        norm_name = _normalize_name(requested)
        
        # Validar Andalucía
        code = PROV_NAME_TO_CODE.get(norm_name)
        andalucia_codes = {"04", "11", "14", "18", "21", "23", "29", "41"}
        
        if not code or code not in andalucia_codes:
            interface.reply_to_message(
                '❌ Provincia no válida. Solo se admiten de Andalucía: Almería, Cádiz, Córdoba, Granada, Huelva, Jaén, Málaga, Sevilla.',
                metadata
            )
            return
            
        requested_province_code = code
        requested_province_name = requested.title()
    else:
        # Si no hay argumentos, usar la provincia por defecto configurada en env.py
        requested_province_code = aemet.province_code()
        requested_province_name = aemet.province.title() if aemet.province else 'Cádiz'

    record = None
    try:
        record = db.aemet_weather_get_latest(province_code=requested_province_code)
    except Exception as e:
        log_p(f"Error leyendo clima: {e}", level="WARN")

    is_old = False
    if record and record.get('created_at'):
        try:
            created = datetime.fromisoformat(record.get('created_at'))
            if datetime.now() - created > timedelta(hours=24):
                is_old = True
        except Exception:
            pass

    # Fetch on-the-fly si no hay datos o están desactualizados
    if not record or not record.get('content') or is_old:
        try:
            if requested_province_code:
                aemet.province = requested_province_name
            
            text = aemet.fetch_province_forecast('hoy')
            if text:
                db.aemet_weather_insert(
                    scope='province',
                    content=text,
                    province=aemet.province,
                    province_code=aemet.province_code(),
                    day='hoy',
                    data_raw=text
                )
                record = db.aemet_weather_get_latest(province_code=aemet.province_code())
                is_old = False

            # Intentar obtener predicción multi-día de la capital para enriquecer tablas del panel web
            try:
                city_code = aemet.resolve_city_code()
                if city_code:
                    daily_data = aemet.fetch_daily_forecast(city_code=city_code)
                    if daily_data:
                        sum_3d = aemet.format_daily_forecast(daily_data, days=3)
                        sum_7d = aemet.format_daily_forecast(daily_data, days=7)
                        db.aemet_forecast_daily_insert(
                            city_code=city_code,
                            city_name=requested_province_name,
                            province=aemet.province or requested_province_name,
                            data_json=daily_data,
                            summary_3d=sum_3d,
                            summary_7d=sum_7d,
                        )
            except Exception as e_daily:
                log_p(f"Error fetching daily forecast for {requested_province_name}: {e_daily}", level="DEBUG")
        except Exception as e:
            log_p(f"Error fetching clima on the fly: {e}", level="WARN")

    if not record or not record.get('content'):
        interface.reply_to_message(
            'Sin datos de clima disponibles todavía. Inténtalo más tarde.',
            metadata,
        )
        return

    body = record.get('content') or ''


    # Añadir advertencia si el dato sigue siendo viejo (falló la petición al vuelo)
    if is_old:
        try:
            created_str = record.get('created_at')
            if created_str:
                created = datetime.fromisoformat(created_str)
                diff = datetime.now() - created
                if diff > timedelta(hours=24):
                    body += f" [⚠️ Datos de hace {diff.days} días (fallo internet)]"
        except Exception:
            pass

    # Añadir dos puntos tras el nombre de la ciudad/provincia si no los tiene
    first_word = body.split(' ', 1)[0]
    if ':' not in first_word:
        body = body.replace(' ', ': ', 1)

    full = body

    # Trocear en hasta 3 mensajes de ~200 caracteres (límite de Meshtastic)
    from functions import split_messages, MESH_MAX_BYTES, MESH_MAX_PARTS
    parts = split_messages(full, max_bytes=MESH_MAX_BYTES, max_parts=MESH_MAX_PARTS)
    if not parts:
        interface.reply_to_message('Sin datos de clima disponibles.', metadata)
        return

    from time import sleep
    for idx, part in enumerate(parts):
        interface.reply_to_message(part, metadata)
        # Pequeña espera entre partes para no saturar la malla
        if idx < len(parts) - 1:
            sleep(2.5)

    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
