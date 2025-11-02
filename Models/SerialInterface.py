
from meshtastic import serial_interface
from pubsub import pub
from functions import log_p, search_command, get_commands_dict
from Models.Node import Node


class SerialInterface:

    lock = False
    node_dict = {}

    def __init__(self, serial_port):

        self.serial_port = serial_port
        self.interface = None
        self.command_dict = get_commands_dict()

    def connect(self):
        self.interface = serial_interface.SerialInterface(devPath=self.serial_port)
        log_p( f"Conectado al dispositivo Meshtastic en puerto {self.serial_port}")
        log_p(f"Esperando mensajes...\n")

        # Suscribirse al topic de mensajes recibidos
        pub.subscribe(self.on_connection, "meshtastic.connection.established")
        pub.subscribe(self.on_receive, "meshtastic.receive")

    def disconnect(self):
        self.interface.close()

    def reconnect(self):
        self.disconnect()
        self.connect()

    def send(self, msg, dest):
        #self.interface.sendText("hello mesh")
        pass

    def receive(self):
        # TODO: plantear trabajar multihilo de forma que recibir quede independienete
        pass

    def on_connection (self, interface):
        """
        Procesa el evento al conectarse al dispositivo Meshtastic

        Args:
            interface: La interfaz de meshtastic que se ha conectado
        """
        log_p("Conexión establecida con el dispositivo Meshtastic")
        self.get_nodes()

    def get_nodes (self):
        """
        Obtiene y almacena la lista de nodos de la red Meshtastic
        """
        if self.interface:
            node_list = self.interface.nodes
            log_p(f"Nodos detectados en la red: {len(node_list)}")

            # Imprimir información de cada nodo
            for node_id, node_info in node_list.items():
                newNodeInfo = Node(node_id)
                newNodeInfo.update_metadata(node_info)
                self.node_dict[node_id] = newNodeInfo
        else:
            log_p("Error: No hay interfaz conectada")

    def get_node_metadata(self, id):
        # TODO: buscar en self.nodes el nodo actual por el ID recibido.
        print(f"id: {id}")
        pass

    def on_receive (self, packet):
        """
        Callback que se ejecuta cuando se recibe un mensaje
        """
        try:
            # Verifico si el paquete contiene un mensaje de texto
            if 'decoded' in packet and 'text' in packet['decoded']:
                msg = packet['decoded']['text']
                from_id = packet.get('fromId', 'Desconocido')
                to_id = packet.get('toId', 'Desconocido')

                # Pedir info del nodo que envía
                fromNodeInfo = self.node_dict.get(from_id, None)

                if not fromNodeInfo:
                    fromNodeInfo = Node(from_id)
                    self.node_dict[from_id] = fromNodeInfo

                if not fromNodeInfo.updated:
                    updated_node_metadata = self.get_node_metadata(from_id)
                    fromNodeInfo.update_metadata(updated_node_metadata)



                metadata = {
                    "node_from": {
                        "id": from_id,
                        "num": packet.get('from', 'N/A'),
                        "role_id": "Desconocido",
                        "uptime": "Desconocido",
                        "public_key": "Desconocido",
                        "is_favorite": "Desconocido",
                        "hop_limit": packet.get('hopLimit', 0),
                    },
                    "node_to": {
                        "id": to_id,
                        "num": packet.get('to', 'N/A'),
                    },
                    "channel": packet.get('channel', None),
                    "is_direct": not (from_id == '^all' or to_id == 0xFFFFFFFF),
                    "rx_snr": packet.get('rxSnr', 0),
                    "rx_rssi": packet.get('rxRssi', 0),
                    "viaMqtt": packet.get('viaMqtt', False),
                }

                print('fromNodeInfo', fromNodeInfo.get_metadata())

                print('Packet: ', packet)
                print('Metadata: ', metadata)

                command, cmd_args = search_command(msg)

                if command:
                    print('ejecutando callback')
                    self.command_dict[command]["callback"](cmd_args, msg, metadata)





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