def weather_callback(interface, args, msg, metadata):
    print('weather')
    
    from Models.Database import Database
    from datetime import datetime, timedelta
    from Models.Aemet import PROV_NAME_TO_CODE, _normalize_name, Aemet

    aemet = Aemet()
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
        requested_province_name = aemet.province.title() if aemet.province else None

    db = Database()
    record = None
    
    try:
        record = db.aemet_weather_get_latest(province_code=requested_province_code)
    except Exception as e:
        print(f"Error leyendo clima: {e}")

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
            aemet = Aemet()
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
        except Exception as e:
            print(f"Error fetching clima on the fly: {e}")

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

    full = f"Tiempo {label}: {body}"

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
            sleep(1)

    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
