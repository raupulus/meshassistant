from datetime import datetime

# Marca temporal de arranque del proceso. Se fija una sola vez al importar este
# módulo (ocurre al inicio del daemon), así /uptime mide el tiempo real encendido
# con independencia de reconexiones del puerto serie.
STARTED_AT = datetime.now()

# Límite de caracteres por mensaje en la malla Meshtastic.
MESH_MAX_LEN = 200
# Máximo de mensajes que puede emitir la respuesta de un comando básico.
MESH_MAX_PARTS = 3


def format_uptime(since: datetime = None) -> str:
    """Devuelve el tiempo transcurrido desde `since` (por defecto STARTED_AT)
    en formato breve español: '3d 4h 12m' (omite las unidades a cero por la
    izquierda). Si es menos de un minuto, devuelve 'menos de 1m'.
    """
    ref = since or STARTED_AT
    delta = datetime.now() - ref
    total = int(delta.total_seconds())
    if total < 0:
        total = 0

    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return ' '.join(parts) if (days or hours or minutes) else 'menos de 1m'


def split_messages(text, max_len: int = MESH_MAX_LEN, max_parts: int = MESH_MAX_PARTS):
    """Trocea un texto en como mucho `max_parts` mensajes de `max_len` caracteres.

    Intenta cortar en un límite de palabra para no partir términos. Si el texto
    excede la capacidad total, el último mensaje termina en '…'.
    """
    text = (text or '').strip()
    if not text:
        return []

    messages = []
    remaining = text
    for i in range(max_parts):
        if not remaining:
            break
        last = (i == max_parts - 1)

        if len(remaining) <= max_len:
            messages.append(remaining)
            remaining = ''
            break

        # Reservar un carácter para el indicador de truncado en el último tramo
        cap = max_len - 1 if last else max_len
        cut = remaining[:cap]
        # Cortar en el último espacio para no partir palabras
        sp = cut.rfind(' ')
        if sp > int(cap * 0.6):
            cut = cut[:sp]
        cut = cut.rstrip()

        if last:
            messages.append((cut + '…').strip())
            remaining = ''
        else:
            messages.append(cut)
            remaining = remaining[len(cut):].lstrip()

    return messages


def reply_long(interface, metadata, text, *, max_parts: int = MESH_MAX_PARTS):
    """Responde troceando el texto en hasta `max_parts` mensajes de la malla.

    Reutiliza split_messages y respeta el límite de ~200 caracteres de Meshtastic,
    esperando 5 s entre partes para no saturar la radio.
    """
    from time import sleep

    parts = split_messages(text, max_len=MESH_MAX_LEN, max_parts=max_parts)
    if not parts:
        parts = [text]
    for idx, part in enumerate(parts):
        interface.reply_to_message(part, metadata)
        if idx < len(parts) - 1:
            sleep(5)


def log_p(message: str, *, level: str = "INFO"):
    """Log condicionado por env.DEBUG.

    Solo imprime si env.DEBUG es True. Añade marca temporal y nivel.
    """
    try:
        import env  # se carga configuración del proyecto
        debug = getattr(env, 'DEBUG', False)
    except Exception:
        debug = False

    if not debug:
        return

    try:
        from datetime import datetime
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        ts = ''

    lvl = (level or 'INFO').upper()
    print(f"[{ts}] [{lvl}] {message}")

def search_command (msg):
    """
    Devuelve el comando y los argumentos si los tuviera.
    """
    # Verificar que el mensaje no esté vacío
    if not msg or len(msg) < 2:
        return None, []

    # Verificar que comience por / o !
    if not msg.startswith('/') and not msg.startswith('!'):
        return None, []

    # Partir en trozos al llegar a espacio
    parts = msg.split()

    # Quedarnos con el primero y quitar el caracter / o !
    comando = parts[0][1:].lower()

    from data import commands_dict

    # Buscar la primera palabra de la cadena en diccionario "command_dict"
    if comando not in commands_dict:
        return None, []

    # Devolver comando y argumentos
    return comando, parts[1:]


def sanitize_text(text: str) -> str:
    """Normaliza y limpia texto para envío/almacenamiento.

    - Convierte a forma Unicode NFKC.
    - Desescapa entidades HTML.
    - Sustituye NBSP y separadores no estándar por espacios.
    - Elimina caracteres de control no imprimibles.
    - Colapsa espacios en blanco múltiples.
    - Recorta extremos.
    """
    if text is None:
        return ''
    try:
        import unicodedata
        import html

        # Desescape HTML & normalización unicode
        t = html.unescape(str(text))
        t = unicodedata.normalize('NFKC', t)

        # Sustituir espacios no estándar
        t = t.replace('\u00A0', ' ').replace('\u2007', ' ').replace('\u202F', ' ')

        # Eliminar caracteres de control excepto \n y \t (luego colapsamos)
        t = ''.join(ch for ch in t if (ch >= ' ' or ch in ('\n', '\t')))

        # Sustituir saltos por espacios y colapsar
        t = ' '.join(t.replace('\r', ' ').replace('\n', ' ').split())

        return t.strip()
    except Exception:
        try:
            return ' '.join(str(text).split()).strip()
        except Exception:
            return ''