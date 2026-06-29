def nodos_callback(interface, args, msg, metadata):
    """/nodos — Resumen de nodos conocidos por el bot.

    Muestra el total de nodos almacenados, cuántos llegan por RF (radio) y
    cuántos vía MQTT (Internet), y cuántos se han oído en las últimas 24 h.
    Los datos salen de la tabla `nodes` (persistente), no solo de memoria.
    """
    try:
        from Models.Database import Database
        ov = Database().nodes_overview(active_hours=24)
        total = ov.get('total', 0)
        rf = ov.get('rf', 0)
        mqtt = ov.get('mqtt', 0)
        active = ov.get('active')

        if total == 0:
            response = 'Aún no hay nodos registrados.'
        else:
            response = f'Nodos: {total} ({rf} RF, {mqtt} MQTT)'
            if active is not None:
                response += f'. Activos 24h: {active}'
            response += '.'
    except Exception as e:
        response = f'No se pudo consultar los nodos: {e}'

    interface.reply_to_message(response, metadata)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
