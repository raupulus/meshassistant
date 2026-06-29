import random

# Respuestas estilo "bola 8 mágica", agrupadas por tono pero mezcladas al elegir.
_RESPUESTAS = [
    # Afirmativas
    'Sin duda alguna.',
    'Es decidido: sí.',
    'Puedes contar con ello.',
    'Sí, rotundamente.',
    'Todo apunta a que sí.',
    'Las señales dicen que sí.',
    'Claro que sí, adelante.',
    # Dudosas / aplazadas
    'Pregunta de nuevo más tarde.',
    'Mejor no decírtelo ahora.',
    'No se puede predecir aún.',
    'Concéntrate y vuelve a preguntar.',
    'La malla está pensándolo…',
    'Ni sí ni no, sino todo lo contrario.',
    # Negativas
    'No cuentes con ello.',
    'Mi respuesta es no.',
    'Mis fuentes dicen que no.',
    'Lo veo poco probable.',
    'Rotundamente no.',
    'No, y van LoRa de pistas.',
]


def bola8_callback(interface, args, msg, metadata):
    """/bola8 (o /8ball) — La bola 8 mágica responde a tu pregunta de sí/no.

    Si no añades pregunta, igualmente da su veredicto. Es solo por diversión.
    """
    respuesta = random.choice(_RESPUESTAS)

    if args:
        response = f'🎱 {respuesta}'
    else:
        response = f'🎱 Hazme una pregunta de sí o no… {respuesta}'

    interface.reply_to_message(response, metadata)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
