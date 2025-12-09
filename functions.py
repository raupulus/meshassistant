

def log_p(x):

    # TODO: controlar desde el .env si estamos en debug o quitar

    return print(x)

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