
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