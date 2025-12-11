from time import sleep
import os
from meshtastic import serial_interface
from pubsub import pub
from functions import log_p, search_command
from data import commands_dict
from Models.Node import Node


class SerialInterface:

    lock = False
    node_dict = {}

    def __init__(self, serial_port):

        self.serial_port = serial_port
        self.interface = None
        self.command_dict = commands_dict

    def connect(self):
        self.interface = serial_interface.SerialInterface(devPath=self.serial_port)
        log_p( f"Conectado al dispositivo Meshtastic en puerto {self.serial_port}")
        log_p(f"Suscribiendo a eventos\n")

        pub.subscribe(self.on_connection, "meshtastic.connection.established")
        #pub.subscribe(self.on_receive, "meshtastic.receive")
        pub.subscribe(self.on_receive_text, "meshtastic.receive.text")
        pub.subscribe(self.on_receive_nodeinfo, "meshtastic.receive.nodeinfo")
        pub.subscribe(self.on_node_update, "meshtastic.node.updated")
        #pub.subscribe(self.on_receive_position, "meshtastic.receive.position")
        pub.subscribe(self.on_receive_user, "meshtastic.receive.user")
        pub.subscribe(self.on_receive_data, "meshtastic.receive.data")

        pub.subscribe(self.on_connection_lost, "meshtastic.connection.lost")
        pub.subscribe(self.on_connection_closed, "meshtastic.connection.closed")

        log_p(f"Esperando mensajes...\n")


    def on_connection_closed(self, interface):
        print('on_connection_closed')

    def on_connection_lost(self, interface):
        print('on_connection_lost')
        sleep(15)

        try:
            if self.interface:
                try:
                    self.interface.close()
                except Exception:
                    pass
                self.interface = None
        except Exception:
            pass

        while not self.interface:
            print('Intentando reconectar')

            if os.path.exists(self.serial_port):
                sleep(5)
                try:
                    self.connect()
                except Exception:
                    pass

            sleep(10)

    def on_receive_position(self, packet, interface):
       print('on_receive_position', packet, interface)

    def on_receive_user(self, packet, interface):
        #print('on_receive_user', packet, interface)
        nodenumber = packet.get('from', None)
        decoded = packet.get('decoded', None)

        if decoded:
            user = decoded.get('user', None)

            if user:
                id = user.get('id', 'Desconocido')

                # Pedir info del nodo que envía
                fromNodeInfo = self.node_dict.get(id, None)

                if not fromNodeInfo:
                    fromNodeInfo = Node(id)
                    self.node_dict[id] = fromNodeInfo

                log_p(f"Nodo Actualizado: {user.get('longName', None)} ({id})")

                fromNodeInfo.update_metadata({
                    "name": user.get('longName', None),
                    "num": nodenumber,
                    "short_name": user.get('shortName', None),
                    "mac_addr": user.get('macaddr', None),
                    "hw_model": user.get('hwModel', None),

                    "snr": packet.get('rxSnr', None),
                    "rssi": packet.get('rxRssi', None),
                    "hop_limit": packet.get('hopLimit', None),
                    "hop_start": packet.get('hopStart', None),
                })



    def on_receive_data(self, packet, interface):
       print('on_receive_data', packet, interface)

    def disconnect(self):
        # Cerrar la interfaz solo si está inicializada
        if self.interface:
            try:
                self.interface.close()
            except Exception:
                pass
            finally:
                self.interface = None
        else:
            # Asegurar estado consistente
            self.interface = None

    def reconnect(self):
        self.disconnect()
        self.connect()

    def send (self, msg, dest=None, channel=0):
        """
        Envía un mensaje a un destino específico o al canal público

        Args:
            msg (str): Mensaje a enviar
            dest (int|str|None): Destino del mensaje. Puede ser:
                - None o "^all": Mensaje al canal público (broadcast)
                - int: ID numérico del nodo (mensaje directo)
                - str: ID en formato "!xxxxxxxx" (mensaje directo)
            channel (int): Número del canal (0-7). Por defecto 0 (canal primario)

        Returns:
            bool: True si se envió correctamente, False en caso contrario

        Ejemplos:
            # Mensaje al canal público
            self.send("Hola a todos")
            self.send("Hola a todos", dest="^all")

            # Mensaje directo por ID numérico
            self.send("Hola privado", dest=123456789)

            # Mensaje directo por ID en formato string
            self.send("Hola privado", dest="!75e1ec00")

            # Mensaje a un canal específico
            self.send("Hola canal 1", channel=1)
        """
        if not self.interface:
            log_p("❌ Error: No hay interfaz conectada")
            return False

        try:
            # Mensaje al canal público (broadcast)
            if dest is None or dest == "^all":
                log_p(
                    f"📢 Enviando mensaje al canal público (canal {channel}): {msg}")
                self.interface.sendText(
                    text=msg,
                    channelIndex=channel
                )
                log_p("✅ Mensaje enviado al canal público")
                return True

            # Mensaje directo a un nodo específico
            else:
                # Convertir el destino a string si es necesario
                dest_str = str(dest) if isinstance(dest, int) else dest

                # Obtener información del nodo destino si está disponible
                node_info = self.node_dict.get(dest, None)
                node_name = "Desconocido"
                if node_info:
                    node_name = node_info.name

                log_p(
                    f"💬 Enviando mensaje directo a {node_name} ({dest_str}): {msg}")

                self.interface.sendText(
                    text=msg,
                    destinationId=dest_str,
                    channelIndex=channel
                )
                log_p(f"✅ Mensaje directo enviado a {node_name}")
                return True

        except Exception as e:
            log_p(f"❌ Error enviando mensaje: {e}")
            return False

    def send_direct (self, msg, node_id):
        """
        Método auxiliar para enviar mensajes directos de forma más explícita

        Args:
            msg (str): Mensaje a enviar
            node_id (int|str): ID del nodo destino

        Returns:
            bool: True si se envió correctamente
        """
        return self.send(msg, dest=node_id)

    def send_to_channel (self, msg, channel=0):
        """
        Método auxiliar para enviar mensajes a un canal público

        Args:
            msg (str): Mensaje a enviar
            channel (int): Número del canal (0-7)

        Returns:
            bool: True si se envió correctamente
        """
        return self.send(msg, dest="^all", channel=channel)

    def reply_to_message (self, msg, metadata):
        """
        Responde automáticamente al remitente de un mensaje
        Detecta si el mensaje original era directo o de grupo y responde apropiadamente

        Args:
            msg (str): Mensaje de respuesta
            metadata (dict): Metadata del mensaje original (como el que creas en on_receive)

        Returns:
            bool: True si se envió correctamente
        """
        is_direct = metadata.get('is_direct', False)
        channel = metadata.get('channel', 0)

        if is_direct:
            # Responder en privado al remitente
            #from_num = metadata['node_from']['num']
            #log_p(f"↩️ Respondiendo en privado al nodo {from_num}")
            #return self.send(msg, dest=from_num)
            from_id = metadata['node_from']['id']
            log_p(f"Respondiendo en privado al nodo {from_id}")
            return self.send(msg, dest=from_id)
        else:
            # Responder en el mismo canal
            log_p(f"↩️ Respondiendo en el canal {channel}")
            return self.send(msg, dest="^all", channel=channel)

    def on_receive_nodeinfo (self, packet, interface):
        """
        TODO: Revisar si entra en este evento, parece que no
        """

        log_p(f"NodeInfo recibido: {packet}")
        pass

    def on_node_update (self, node, interface):
        # TODO: Parece que aquí entra al reconectar dispositivo
        log_p(f"Nodo conectado actualizado, on_node_update")


    def on_connection (self, interface):
        """
        Procesa el evento al conectarse al dispositivo Meshtastic

        Args:
            interface: La interfaz de meshtastic que se ha conectado
        """
        log_p("Conexión establecida con el dispositivo Meshtastic")
        self.get_nodes()

    def traceroute(self, node_id: str, timeout: float = 10.0):
        """Ejecuta un TraceRoute real usando Meshtastic `sendTraceRoute` y capta la salida textual.

        Compatibilidad de llamada (variantes probadas en orden):
          1) sendTraceRoute(node_id, 3, False, callback)
          2) sendTraceRoute(node_id, callback)
          3) sendTraceRoute(node_id, 3, False)
          4) sendTraceRoute(node_id)
          5) sendTraceRoute(destinationId=node_id, onResponse=callback)
          6) sendTraceRoute(id=node_id, onResponse=callback)
          7) sendTraceRoute(destinationId=node_id)

        Devuelve: dict con claves:
          - text: str con la salida completa capturada (incluye líneas "Route traced ...")
          - forward: lista de hops hacia destino (cada item: {id: str, snr: float|None})
          - backward: lista de hops de regreso (cada item: {id: str, snr: float|None})
        """
        if not self.interface:
            raise RuntimeError("Interfaz Meshtastic no conectada")

        send_fn = getattr(self.interface, 'sendTraceRoute', None)
        if send_fn is None or not callable(send_fn):
            raise AttributeError("La interfaz Meshtastic no soporta sendTraceRoute()")

        # Callback (por si la lib lo usa) – mantenemos por si aporta datos
        results = []

        def _on_response(*args, **kwargs):
            try:
                if args and isinstance(args[0], dict) and not kwargs:
                    results.append(args[0])
                else:
                    results.append({'args': args, 'kwargs': kwargs})
            except Exception:
                results.append({'repr': repr((args, kwargs))})

        # Capturar la salida textual que imprime la librería durante el trace
        import time
        import io
        import contextlib

        buf_out = io.StringIO()
        buf_err = io.StringIO()

        # Intentar variantes en orden de máxima compatibilidad (posicionales primero)
        tried: list[str] = []
        called = False

        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            # 1) Posicional completa con hopLimit e isRepeat y callback
            try:
                send_fn(node_id, 3, False, _on_response)
                called = True
            except TypeError as e:
                tried.append(str(e))

            # 2) Posicional con callback como segundo argumento
            if not called:
                try:
                    send_fn(node_id, _on_response)
                    called = True
                except TypeError as e:
                    tried.append(str(e))

            # 3) Posicional sin callback pero con hopLimit/isRepeat
            if not called:
                try:
                    send_fn(node_id, 3, False)
                    called = True
                except TypeError as e:
                    tried.append(str(e))

            # 4) Posicional mínimo solo id
            if not called:
                try:
                    send_fn(node_id)
                    called = True
                except TypeError as e:
                    tried.append(str(e))

            # 5) Keywords modernas (por si la versión sí las soporta)
            if not called:
                try:
                    send_fn(destinationId=node_id, onResponse=_on_response)
                    called = True
                except TypeError as e:
                    tried.append(str(e))
                    try:
                        send_fn(id=node_id, onResponse=_on_response)
                        called = True
                    except TypeError as e2:
                        tried.append(str(e2))

            # 6) Último recurso: keyword mínima sin callback
            if not called:
                try:
                    send_fn(destinationId=node_id)
                    called = True
                except Exception as e:
                    tried.append(str(e))

            if not called:
                # Dejar la salida capturada hasta ahora y lanzar error
                text_now = (buf_out.getvalue() or '') + (buf_err.getvalue() or '')
                raise TypeError("sendTraceRoute no pudo ser invocado de forma compatible; errores: " + " | ".join(tried) + f"\n{text_now}")

            # Ventana de espera para que se impriman las rutas
            start = time.time()
            last_len = 0
            while time.time() - start < timeout:
                # Si el callback recibe algo, ampliamos un poco la espera
                if len(results) != last_len:
                    last_len = len(results)
                    time.sleep(0.3)
                time.sleep(0.2)

        text = (buf_out.getvalue() or '')
        err_text = (buf_err.getvalue() or '')
        if err_text and (not text):
            text = err_text

        # Parsear las líneas para extraer hops de ida y regreso
        def _parse_forward_hops(txt: str):
            import re
            hops = []
            lines = [l.strip() for l in txt.splitlines() if l.strip()]
            # Buscar la línea inmediatamente posterior a "Route traced towards destination:"
            for i, l in enumerate(lines):
                if l.lower().startswith('route traced towards destination'):
                    if i + 1 < len(lines):
                        path_line = lines[i + 1]
                        # Split por flechas
                        parts = [p.strip() for p in path_line.split('-->')]
                        # Cada parte puede ser "!id (X dB)" o solo "!id"
                        # El primer elemento es el origen; hops son los siguientes
                        def parse_part(part: str):
                            m = re.search(r'(![0-9a-fA-F]+)', part)
                            node = m.group(1) if m else None
                            m2 = re.search(r'\(([-+]?\d+(?:\.\d+)?)\s*dB\)', part)
                            snr = float(m2.group(1)) if m2 else None
                            return node, snr
                        parsed = [parse_part(p) for p in parts]
                        # Tomar solo después del primero como hops
                        for node, snr in parsed[1:]:
                            if node:
                                hops.append({'id': node, 'snr': snr})
                    break
            return hops

        def _parse_backward_hops(txt: str):
            import re
            hops = []
            lines = [l.strip() for l in txt.splitlines() if l.strip()]
            # Buscar la línea inmediatamente posterior a "Route traced back to us:"
            for i, l in enumerate(lines):
                if l.lower().startswith('route traced back to us'):
                    if i + 1 < len(lines):
                        path_line = lines[i + 1]
                        parts = [p.strip() for p in path_line.split('-->')]
                        def parse_part(part: str):
                            m = re.search(r'(![0-9a-fA-F]+)', part)
                            node = m.group(1) if m else None
                            m2 = re.search(r'\(([-+]?\d+(?:\.\d+)?)\s*dB\)', part)
                            snr = float(m2.group(1)) if m2 else None
                            return node, snr
                        parsed = [parse_part(p) for p in parts]
                        # El primer elemento es el destino y los siguientes los saltos de vuelta
                        for node, snr in parsed[1:]:
                            if node:
                                hops.append({'id': node, 'snr': snr})
                    break
            return hops

        forward_hops = _parse_forward_hops(text)
        backward_hops = _parse_backward_hops(text)

        return {
            'text': text.strip(),
            'forward': forward_hops,
            'backward': backward_hops,
        }

    def get_nodes (self):
        """
        Obtiene y almacena la lista de nodos de la red Meshtastic
        """
        if self.interface:
            node_list = self.interface.nodes
            log_p(f"Nodos detectados en la red: {len(node_list)}")

            # Instancio cada nodo y lo almaceno en un diccionario
            for node_num, node_info in node_list.items():
                user = node_info.get('user', { })
                id = user.get('id', 'Desconocido')
                newNodeInfo = Node(id)

                newNodeInfo.update_metadata({
                    "name": user.get('longName', None),
                    "num": node_num,
                    "short_name": user.get('shortName', None),
                    "mac_addr": user.get('macaddr', None),
                    "hw_model": user.get('hwModel', None),

                    "snr": node_info.get('snr', None),
                    #"rssi": packet.get('rxRssi', None),
                    #"hop_limit": packet.get('hopLimit', None),
                    #"hop_start": packet.get('hopStart', None),
                    #"last_heard": node_info.get('lastHeard', None),
                    "hops": node_info.get('hopsAway', None),
                    "is_favorite": node_info.get('isFavorite', None),
                })

                newNodeInfo.update_metadata(node_info)
                self.node_dict[id] = newNodeInfo
        else:
            log_p("Error: No hay interfaz conectada")

    def on_receive_text (self, packet, interface):
        """
        Callback que se ejecuta cuando se recibe un mensaje
        """
        try:
            # Verifico si el paquete contiene un mensaje de texto
            if 'decoded' in packet and 'text' in packet['decoded']:
                msg = packet['decoded']['text']
                from_id = packet.get('fromId', 'Desconocido')
                to_id = packet.get('toId', 'Desconocido')
                to_num = packet.get('to', 'N/A')

                if to_id == '^all' or to_num == 0xFFFFFFFF:
                    is_direct = False
                else:
                    is_direct = True

                # Pedir info del nodo que envía
                fromNodeInfo = self.node_dict.get(from_id, None)

                if not fromNodeInfo:
                    fromNodeInfo = Node(from_id)
                    self.node_dict[from_id] = fromNodeInfo

                fromNodeInfo.update_metadata({
                    #"name": user.get('longName', None),
                    "num": packet.get('from', None),
                    #"short_name": user.get('shortName', None),
                    #"mac_addr": user.get('macaddr', None),
                    #"hw_model": user.get('hwModel', None),

                    "snr": packet.get('rxSnr', None),
                    "rssi": packet.get('rxRssi', None),
                    "hop_limit": packet.get('hopLimit', None),
                    "hop_start": packet.get('hopStart', None),

                    "is_direct": is_direct,
                    "via_mqtt": packet.get('viaMqtt', False),
                })


                metadata = {
                    "node_from": fromNodeInfo.get_metadata(),
                    "node_to": {
                        "id": to_id,
                        "num": packet.get('to', 'N/A'),
                    },
                    "channel": packet.get('channel', None),
                    "is_direct": is_direct,
                    "rx_snr": fromNodeInfo.snr,
                    "rx_rssi": fromNodeInfo.rssi,
                    "via_mqtt": fromNodeInfo.via_mqtt,
                }

                # Busco comando y argumentos en el mensaje
                command, cmd_args = search_command(msg)

                # Si el mensaje recibido es un comando, ejecutarlo
                if command:
                    # Directo responde siempre, en grupo solo a ciertos comandos
                    if not is_direct and not self.command_dict[command][
                        'in_group']:
                        return

                    self.command_dict[command]["callback"](self,
                                                           cmd_args, msg,
                                                           metadata)

        except Exception as e:
            log_p(f"Error procesando paquete: {e}")