def stats_callback(interface, args, msg, metadata):
    """/stats — Estadísticas del bot y de la malla.

    Muestra comandos atendidos (hoy/total), el comando más usado, pings
    registrados, nodos conocidos (RF/MQTT), encuestas activas y el tiempo
    encendido. Todo se lee de la BD local.
    """
    from functions import reply_long, format_uptime

    try:
        from Models.Database import Database
        s = Database().stats_summary()

        top_cmd, top_n = s.get('cmd_top', (None, 0))
        partes = [
            f"Comandos: {s.get('cmd_today', 0)} hoy / {s.get('cmd_total', 0)} total",
        ]
        if top_cmd:
            partes.append(f"top /{top_cmd} ({top_n})")
        partes.append(f"pings {s.get('pings_total', 0)}")
        partes.append(
            f"nodos {s.get('nodes_total', 0)} ({s.get('nodes_rf', 0)} RF/{s.get('nodes_mqtt', 0)} MQTT)"
        )
        if s.get('encuestas_activas'):
            partes.append(f"encuestas activas {s.get('encuestas_activas')}")
        partes.append(f"encendido {format_uptime()}")

        response = 'Stats: ' + '. '.join(partes) + '.'
    except Exception as e:
        response = f'No se pudieron calcular las estadísticas: {e}'

    reply_long(interface, metadata, response)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
