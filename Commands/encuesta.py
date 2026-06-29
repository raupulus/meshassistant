import re
from datetime import datetime

# Límites de tamaño pensados para la malla (mensajes cortos)
MAX_OPCIONES = 6
MIN_OPCIONES = 2
MAX_PREGUNTA = 120
MAX_OPCION = 40

AYUDA = (
    'Encuesta: /encuesta nueva ¿Pregunta? | opción1 | opción2 [| ...] (dias=N opcional, 1-30, def 7). '
    'Votar: /encuesta voto <id> <nº>. Ver: /encuesta ver <id>. '
    'Lista: /encuesta. Cerrar/borrar (solo dueño): /encuesta cerrar|borrar <id>.'
)


def _fmt_fecha(iso):
    try:
        return datetime.fromisoformat(iso).strftime('%d/%m')
    except Exception:
        return '?'


def _resultados_texto(db, enc):
    res = db.encuesta_results(enc['id'])
    counts = res['counts']
    total = res['total']
    estado = 'activa' if enc.get('status') == 'active' else 'cerrada'
    cab = f"Encuesta #{enc['id']} ({estado}"
    if enc.get('status') == 'active' and enc.get('ends_at'):
        cab += f", cierra {_fmt_fecha(enc['ends_at'])}"
    cab += f"): {enc['question']}"

    lineas = []
    for i, op in enumerate(enc['options']):
        n = counts[i] if i < len(counts) else 0
        pct = int(round(100 * n / total)) if total else 0
        lineas.append(f"{i + 1}) {op}: {n} ({pct}%)")
    return f"{cab} — " + ' '.join(lineas) + f". Total {total} voto(s)."


def encuesta_callback(interface, args, msg, metadata):
    """/encuesta — Encuestas comunitarias.

    Cada nodo puede tener UNA encuesta activa a la vez. Cualquier nodo puede
    votar cualquier encuesta (y cambiar su voto). Solo el nodo que la crea puede
    cerrarla o borrarla. Duración elegible entre 1 y 30 días (7 por defecto).
    Subcomandos: nueva, voto, ver/resultados, lista, cerrar, borrar, ayuda.
    """
    from functions import reply_long

    node_from = (metadata or {}).get('node_from') or {}
    owner_id = node_from.get('id')

    try:
        from Models.Database import Database
        db = Database()
    except Exception as e:
        interface.reply_to_message(f'Error de base de datos: {e}', metadata)
        return

    sub = (args[0].lower() if args else '').strip()

    # ---- Ayuda ----
    if sub in ('ayuda', 'help', 'info'):
        reply_long(interface, metadata, AYUDA)
        return

    # ---- Lista de activas (sin args o 'lista') ----
    if not args or sub in ('lista', 'list'):
        activas = db.encuesta_list_active(limit=8)
        if not activas:
            interface.reply_to_message('No hay encuestas activas. Crea una con /encuesta ayuda', metadata)
            return
        trozos = [f"#{e['id']} {e['question']}" for e in activas]
        reply_long(interface, metadata, 'Encuestas activas: ' + ' · '.join(trozos))
        return

    # ---- Crear ----
    if sub in ('nueva', 'new', 'crear'):
        if not owner_id:
            interface.reply_to_message('No se pudo identificar tu nodo para crear la encuesta.', metadata)
            return

        # ¿Ya tiene una activa?
        existente = db.encuesta_get_active_by_owner(owner_id)
        if existente:
            interface.reply_to_message(
                f"Ya tienes la encuesta #{existente['id']} activa. Ciérrala con /encuesta cerrar {existente['id']} antes de crear otra.",
                metadata,
            )
            return

        # Texto tras la palabra 'nueva' (o new/crear)
        cuerpo = re.sub(r'^\s*[/!]encuesta\s+\w+\s*', '', msg, flags=re.IGNORECASE)

        # Extraer dias=N SOLO si va al final del texto (punto 4 de la revisión).
        # Anclar en $ evita mutilar la cadena si alguien escribe "dias=3" dentro
        # de la pregunta o de una opción (p.ej. "¿En cuantos dias=3? | 3 | 5").
        dias = 7
        m = re.search(r'\s*\bdias\s*[=:]\s*(\d+)\s*$', cuerpo, flags=re.IGNORECASE)
        if m:
            dias = int(m.group(1))
            cuerpo = cuerpo[:m.start()]

        partes = [p.strip() for p in cuerpo.split('|')]
        partes = [p for p in partes if p]
        if len(partes) < 1 + MIN_OPCIONES:
            interface.reply_to_message(
                f'Faltan datos. Uso: /encuesta nueva ¿Pregunta? | op1 | op2 (mín. {MIN_OPCIONES} opciones).',
                metadata,
            )
            return

        pregunta = partes[0][:MAX_PREGUNTA]
        opciones = [o[:MAX_OPCION] for o in partes[1:1 + MAX_OPCIONES]]
        if len(opciones) < MIN_OPCIONES:
            interface.reply_to_message(f'Necesitas al menos {MIN_OPCIONES} opciones.', metadata)
            return

        try:
            new_id = db.encuesta_create(owner_node_id=owner_id, question=pregunta,
                                        options=opciones, days=dias)
        except Exception as e:
            interface.reply_to_message(f'No se pudo crear la encuesta: {e}', metadata)
            return

        dias_norm = max(1, min(30, dias))
        ops_txt = ' '.join(f'{i + 1}){o}' for i, o in enumerate(opciones))
        reply_long(
            interface, metadata,
            f"Encuesta #{new_id} creada ({dias_norm} día(s)): {pregunta} — {ops_txt}. "
            f"Vota con /encuesta voto {new_id} <nº>.",
        )
        return

    # ---- Votar ----
    if sub in ('voto', 'votar', 'vote'):
        if len(args) < 3:
            interface.reply_to_message('Uso: /encuesta voto <id> <nº de opción>', metadata)
            return
        try:
            enc_id = int(args[1])
            opcion = int(args[2])
        except ValueError:
            interface.reply_to_message('Id y opción deben ser números. Ej: /encuesta voto 5 2', metadata)
            return

        enc = db.encuesta_get(enc_id)
        if not enc:
            interface.reply_to_message(f'No existe la encuesta #{enc_id}.', metadata)
            return
        if enc.get('status') != 'active':
            interface.reply_to_message(f'La encuesta #{enc_id} está cerrada.', metadata)
            return
        if not (1 <= opcion <= len(enc['options'])):
            interface.reply_to_message(
                f'Opción fuera de rango (1-{len(enc["options"])}).', metadata)
            return
        if not owner_id:
            interface.reply_to_message('No se pudo identificar tu nodo para votar.', metadata)
            return

        estado = db.encuesta_vote(enc_id, owner_id, opcion - 1)
        elegido = enc['options'][opcion - 1]
        if estado == 'new':
            interface.reply_to_message(f"Voto registrado en #{enc_id}: '{elegido}'.", metadata)
        elif estado == 'changed':
            interface.reply_to_message(f"Voto cambiado en #{enc_id} a '{elegido}'.", metadata)
        else:
            interface.reply_to_message(f"Ya habías votado '{elegido}' en #{enc_id}.", metadata)
        return

    # ---- Ver resultados ----
    if sub in ('ver', 'resultados', 'stats', 'resultado'):
        if len(args) < 2:
            interface.reply_to_message('Uso: /encuesta ver <id>', metadata)
            return
        try:
            enc_id = int(args[1])
        except ValueError:
            interface.reply_to_message('El id debe ser un número. Ej: /encuesta ver 5', metadata)
            return
        enc = db.encuesta_get(enc_id)
        if not enc:
            interface.reply_to_message(f'No existe la encuesta #{enc_id}.', metadata)
            return
        reply_long(interface, metadata, _resultados_texto(db, enc))
        return

    # ---- Cerrar / Borrar (solo dueño) ----
    if sub in ('cerrar', 'close', 'finalizar', 'borrar', 'eliminar', 'delete'):
        if len(args) < 2:
            interface.reply_to_message(f'Uso: /encuesta {sub} <id>', metadata)
            return
        try:
            enc_id = int(args[1])
        except ValueError:
            interface.reply_to_message('El id debe ser un número.', metadata)
            return
        enc = db.encuesta_get(enc_id)
        if not enc:
            interface.reply_to_message(f'No existe la encuesta #{enc_id}.', metadata)
            return
        if enc.get('owner_node_id') != owner_id:
            interface.reply_to_message('Solo el nodo que creó la encuesta puede cerrarla o borrarla.', metadata)
            return

        if sub in ('borrar', 'eliminar', 'delete'):
            ok = db.encuesta_delete(enc_id, owner_id)
            interface.reply_to_message(
                f'Encuesta #{enc_id} borrada.' if ok else f'No se pudo borrar #{enc_id}.', metadata)
        else:
            ok = db.encuesta_close(enc_id, owner_id)
            if ok:
                reply_long(interface, metadata, 'Encuesta cerrada. ' + _resultados_texto(db, db.encuesta_get(enc_id)))
            else:
                interface.reply_to_message(f'La encuesta #{enc_id} ya estaba cerrada.', metadata)
        return

    # ---- Subcomando desconocido ----
    interface.reply_to_message('Subcomando no reconocido. Usa /encuesta ayuda.', metadata)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
