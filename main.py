

from meshtastic import serial_interface
from pubsub import pub

from functions import log_p

import env

# Obtener la ruta del dispositivo serial desde .env
SERIAL_DEVICE_PATH = env.SERIAL_DEVICE_PATH




def example_callback(msg, metadata):
    """
    Metadata podría ser el canal, usuario etc etc
    :param msg:
    :param metadata:
    :return:
    """
    log_p(f"Received message: {msg}")
    log_p(f"Metadata: {metadata}")


def help_callback(msg, metadata):
    log_p(f"Received message: {msg}")
    log_p(f"Metadata: {metadata}")




command_dict = {
    "help": {
        "callback": help_callback,
        "info": "Muestra este mensaje de ayuda"
    }
}


def search_command (msg):
    """
    Debe devolver el comando y los argumentos.

    /help meteo fgds gsdf gsdf g

    :param msg:
    :return:
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

    # Buscar la primera palabra de la cadena en diccionario "command_dict"
    if comando not in command_dict:
        return None, []

    # Devolver comando y argumentos
    return comando, parts[1:]


def on_receive(packet, interface):
    """
    Callback que se ejecuta cuando se recibe un mensaje
    """
    try:
        # Verificar si el paquete contiene un mensaje de texto
        if 'decoded' in packet and 'text' in packet['decoded']:
            msg = packet['decoded']['text']

            print("packet:", packet)

            metadata = {
                "node_from": {
                    "id": packet.get('fromId', 'Desconocido'),
                    "num": packet.get('from', 'N/A'),
                    "role_id": "Desconocido",
                    "uptime": "Desconocido",
                    "public_key": "Desconocido",
                    "is_favorite": "Desconocido",
                    "hop_limit": packet.get('hopLimit', 0),
                },
                "node_to": {
                    "id": packet.get('toId', 'Desconocido'),
                    "num": packet.get('to', 'N/A'),
                    "role_id": "Desconocido",
                    "uptime": "Desconocido",
                    "public_key": "Desconocido",
                    "is_favorite": "Desconocido",
                },
                "channel": packet.get('channel', None),
                "is_direct": not (packet.get('toId', 'Desconocido') == '^all' or packet.get('to', 'N/A') == 0xFFFFFFFF),
            }

            command, cmd_args = search_command(msg)

            if command:
                print('ejecutando callback')
                command_dict[command]["callback"](msg, metadata)







            ## DUplicada, borrar cuando depure


            # Obtener información del remitente
            from_id = packet.get('fromId', 'Desconocido')
            from_num = packet.get('from', 'N/A')
            to_id = packet.get('toId', 'Desconocido')
            to_num = packet.get('to', 'N/A')

            # Determinar si es mensaje directo o de grupo
            # En Meshtastic, si el destino es "^all" o un canal, es mensaje de grupo
            if to_id == '^all' or to_num == 0xFFFFFFFF:
                tipo = "📢 GRUPO"
            else:
                tipo = "💬 DIRECTO"

            # Obtener canal si existe

            canal = packet.get('channel', 0)

            # Imprimir el mensaje formateado
            log_p(f"\n{'=' * 60}")
            log_p(f"{tipo}")
            log_p(f"De: {from_id} ({from_num})")
            log_p(f"Para: {to_id} ({to_num})")
            log_p(f"Canal: {canal}")
            log_p(f"Mensaje: {msg}")
            log_p(f"{'=' * 60}\n")




    except Exception as e:
        log_p(f"Error procesando paquete: {e}")



def main():
    log_p("Iniciando receptor de mensajes Meshtastic por UART...")
    log_p("Presiona Ctrl+C para salir\n")

    interface = serial_interface.SerialInterface(devPath=SERIAL_DEVICE_PATH)
    log_p(f"Conectado al dispositivo Meshtastic en puerto {SERIAL_DEVICE_PATH}")
    log_p(f"Esperando mensajes...\n")

    # Suscribirse al topic de mensajes recibidos
    pub.subscribe(on_receive, "meshtastic.receive")

    # Mantener el script ejecutándose
    while True:
        pass




    print('Prueba de parsear comando:', search_command("/help meteo asd1 gsdf2"))
    print('Prueba de parsear comando sin args:', search_command("/help"))
    print('Prueba de parsear comando que no existe:', search_command("/aguacate meteo asd1 gsdf2 gsdf3 g4"))








if __name__ == "__main__":
    main()
