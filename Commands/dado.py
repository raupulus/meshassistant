import random
import re


def dado_callback(interface, args, msg, metadata):
    """/dado — Tira uno o varios dados.

    Uso:
      /dado            → 1 dado de 6 caras
      /dado 20         → 1 dado de 20 caras (d20)
      /dado 2d6        → 2 dados de 6 caras (suma + desglose)
    Límites: 1-10 dados, 2-1000 caras.
    """
    n_dados = 1
    caras = 6

    arg = (args[0].lower() if args else '').strip()
    if arg:
        m = re.fullmatch(r'(\d+)d(\d+)', arg)
        if m:
            n_dados = int(m.group(1))
            caras = int(m.group(2))
        elif arg.isdigit():
            caras = int(arg)
        else:
            interface.reply_to_message('Uso: /dado, /dado 20 o /dado 2d6', metadata)
            return

    # Validar límites
    if not (1 <= n_dados <= 10) or not (2 <= caras <= 1000):
        interface.reply_to_message('Límites: 1-10 dados y 2-1000 caras.', metadata)
        return

    tiradas = [random.randint(1, caras) for _ in range(n_dados)]

    if n_dados == 1:
        response = f'🎲 d{caras}: {tiradas[0]}'
    else:
        total = sum(tiradas)
        response = f'🎲 {n_dados}d{caras}: {total} ({" + ".join(str(t) for t in tiradas)})'

    interface.reply_to_message(response, metadata)
    # El registro en commands_sent se hace de forma centralizada en
    # SerialInterface.on_receive_text tras ejecutar el callback.
