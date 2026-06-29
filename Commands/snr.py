def snr_callback(interface, args, msg, metadata):
    """/snr — Calidad de señal del nodo pasarela y media de la malla.

    El nodo del bot está en interior; sale a la malla a través de un nodo
    propio en la azotea (nombre corto configurable en MESH_GATEWAY_SHORT_NAME,
    por defecto 'RAU0'). Ese es el SNR que de verdad importa, así que se muestra
    primero, junto con la media de SNR del resto de nodos RF conocidos.
    """
    try:
        import env
        gateway = getattr(env, 'MESH_GATEWAY_SHORT_NAME', 'RAU0') or 'RAU0'
    except Exception:
        gateway = 'RAU0'

    try:
        from Models.Database import Database
        db = Database()

        node = db.get_node_by_short_name(gateway)
        avg = db.snr_average(exclude_mqtt=True)

        partes = []
        if node and node.get('snr') is not None:
            snr = node.get('snr')
            hops = node.get('hops')
            txt = f'SNR {gateway}: {snr:.1f} dB'
            if hops is not None:
                txt += f' ({hops} hops)'
            partes.append(txt)
        else:
            partes.append(f'SNR {gateway}: sin dato aún')

        if avg.get('avg') is not None:
            partes.append(f'Media malla RF: {avg["avg"]:.1f} dB ({avg["count"]} nodos)')

        response = '. '.join(partes) + '.'
    except Exception as e:
        response = f'No se pudo consultar el SNR: {e}'

    interface.reply_to_message(response, metadata)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
