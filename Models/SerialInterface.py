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

    # Eventos pubsub gestionados por esta clase: (handler, topic). Se usa para
    # suscribir y desuscribir de forma simétrica y evitar suscripciones duplicadas
    # al reconectar.
    def _subscriptions(self):
        return [
            (self.on_connection, "meshtastic.connection.established"),
            (self.on_receive_text, "meshtastic.receive.text"),
            (self.on_receive_nodeinfo, "meshtastic.receive.nodeinfo"),
            (self.on_node_update, "meshtastic.node.updated"),
            (self.on_receive_user, "meshtastic.receive.user"),
            (self.on_receive_position, "meshtastic.receive.position"),
            (self.on_receive_data, "meshtastic.receive.telemetry"),
            (self.on_receive_data, "meshtastic.receive.data"),
            (self.on_receive_data, "meshtastic.receive.data.TELEMETRY_APP"),
            (self.on_receive_data, "meshtastic.receive.data.67"),
            (self.on_receive_data, "meshtastic.receive"),
            (self.on_connection_lost, "meshtastic.connection.lost"),
            (self.on_connection_closed, "meshtastic.connection.closed"),
        ]

    def __init__(self, serial_port):

        self.serial_port = serial_port
        self.interface = None
        self.command_dict = commands_dict
        # Bandera atómica (bool en CPython) que marca on_connection_lost. La
        # reconexión real la realiza el hilo principal en main.loop(), nunca el
        # hilo 'publishing' de Meshtastic (que reparte los mensajes recibidos).
        self._needs_reconnect = False

    def _subscribe(self):
        for handler, topic in self._subscriptions():
            pub.subscribe(handler, topic)

    def _unsubscribe(self):
        for handler, topic in self._subscriptions():
            try:
                pub.unsubscribe(handler, topic)
            except Exception:
                pass

    def connect(self):
        # Evitar suscripciones acumuladas si se reconecta.
        self._unsubscribe()
        try:
            self.interface = serial_interface.SerialInterface(devPath=self.serial_port)
            self._needs_reconnect = False
            log_p(f"Conectado al dispositivo Meshtastic en puerto {self.serial_port}")
            log_p(f"Suscribiendo a eventos\n")
            self._subscribe()
            log_p(f"Esperando mensajes...\n")
        except Exception as e:
            log_p(f"Error al conectar con Meshtastic en {self.serial_port}: {e}", level="WARN")
            self._needs_reconnect = True
            self.interface = None


    def on_connection_closed(self, interface):
        log_p("on_connection_closed", level="WARN")
        self._needs_reconnect = True

    def on_connection_lost(self, interface):
        # CRÍTICO: este callback corre en el hilo 'publishing' de Meshtastic, el
        # mismo que entrega los mensajes recibidos. NO debe bloquear ni reconectar
        # aquí: solo marca la bandera y retorna. La reconexión la hace main.loop().
        log_p("on_connection_lost", level="WARN")
        self._needs_reconnect = True

    def reconnect_if_needed(self):
        """Reconexión ordenada, pensada para llamarse desde el hilo principal.

        Cierra el interfaz viejo por completo, espera a que exista el dispositivo
        y reconecta. Si falla, deja la bandera activa para reintentar en la
        siguiente vuelta del loop. Devuelve True si (re)conectó en esta llamada.
        """
        if not self._needs_reconnect:
            return False

        log_p("Reconexión solicitada: cerrando interfaz previa...", level="WARN")
        self._unsubscribe()
        self.disconnect()

        if not os.path.exists(self.serial_port):
            log_p(f"Dispositivo {self.serial_port} aún no presente; reintentaré.",
                  level="WARN")
            import time
            time.sleep(5)
            return False

        try:
            self.connect()
            if self.interface is not None:
                log_p("Reconexión completada con éxito", level="WARN")
                return True
            else:
                self._needs_reconnect = True
                import time
                time.sleep(5)
                return False
        except Exception as e:
            log_p(f"Fallo al reconectar: {e}", level="WARN")
            self._needs_reconnect = True
            import time
            time.sleep(5)
            return False

    def on_receive_position(self, packet, interface):
        log_p(f"on_receive_position: {packet}", level="DEBUG")
        try:
            decoded = packet.get('decoded', {})
            pos = decoded.get('position', {}) if isinstance(decoded, dict) else {}
            if pos:
                from Models.EventBroadcaster import broadcast_event
                lat = pos.get('latitude')
                if lat is None and pos.get('latitudeI') is not None:
                    lat = pos.get('latitudeI') / 1e7
                lon = pos.get('longitude')
                if lon is None and pos.get('longitudeI') is not None:
                    lon = pos.get('longitudeI') / 1e7

                broadcast_event("position_rx", {
                    "id": packet.get('fromId') or str(packet.get('from')),
                    "lat": lat,
                    "lon": lon,
                    "alt": pos.get('altitude'),
                    "time": pos.get('time'),
                })
        except Exception:
            pass

    def on_receive_user(self, packet, interface):
        # log_p(f"on_receive_user: {packet}", level="DEBUG")
        nodenumber = packet.get('from', None)
        decoded = packet.get('decoded', None)

        if decoded:
            user = decoded.get('user', None)

            if user:
                id = user.get('id', 'Desconocido')

                # Comprobar vigilancia / ignorados
                try:
                    from Models.MeshWatcher import MeshWatcher
                    if MeshWatcher.is_ignored(id):
                        return
                    MeshWatcher.inspect_packet(packet)
                except Exception:
                    pass

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
                    "role": user.get('role', None),

                    "snr": packet.get('rxSnr', None),
                    "rssi": packet.get('rxRssi', None),
                    "hop_limit": packet.get('hopLimit', None),
                    "hop_start": packet.get('hopStart', None),
                })

                try:
                    from Models.EventBroadcaster import broadcast_event
                    broadcast_event("node_updated", {
                        "id": id,
                        "num": nodenumber,
                        "name": user.get('longName'),
                        "short_name": user.get('shortName'),
                        "mac_addr": user.get('macaddr'),
                        "hw_model": user.get('hwModel'),
                        "role": user.get('role'),
                        "snr": packet.get('rxSnr'),
                        "rssi": packet.get('rxRssi'),
                        "hops": fromNodeInfo.hops,
                    })
                except Exception:
                    pass

    def on_receive_data(self, packet, interface):
        log_p(f"on_receive_data: {packet}", level="DEBUG")
        try:
            if not isinstance(packet, dict):
                return

            decoded = packet.get('decoded', {})
            from Models.EventBroadcaster import broadcast_event
            
            # Resolver node_id canónico
            from_num = packet.get('from')
            from_node_id = packet.get('fromId')
            if not from_node_id and from_num is not None:
                try:
                    from_node_id = f"!{int(from_num):08x}"
                except Exception:
                    from_node_id = str(from_num)

            # Comprobar vigilancia y descarte de ignorados
            try:
                from Models.MeshWatcher import MeshWatcher
                from_info = self.node_dict.get(from_node_id) if from_node_id else None
                if MeshWatcher.inspect_packet(packet, from_info):
                    return
            except Exception:
                pass

            # Extraer telemetría flexible
            telemetry = decoded.get('telemetry') or decoded.get('deviceMetrics') or decoded.get('device_metrics') or packet.get('telemetry') or packet.get('deviceMetrics') or {}
            dev_m = telemetry.get('deviceMetrics') or telemetry.get('device_metrics') or telemetry if isinstance(telemetry, dict) else {}

            if isinstance(dev_m, dict) and dev_m:
                battery_lvl = dev_m.get('batteryLevel') if dev_m.get('batteryLevel') is not None else dev_m.get('battery')
                voltage_val = dev_m.get('voltage')
                uptime_val = dev_m.get('uptimeSeconds') if dev_m.get('uptimeSeconds') is not None else dev_m.get('uptime')
                ch_util = dev_m.get('channelUtilization') if dev_m.get('channelUtilization') is not None else dev_m.get('channel_utilization')
                air_tx = dev_m.get('airUtilTx') if dev_m.get('airUtilTx') is not None else dev_m.get('air_util_tx')

                # Persistir telemetría en BD si el nodo existe
                if from_node_id:
                    try:
                        from Models.Database import Database
                        db = Database()
                        db_data = {}
                        if battery_lvl is not None:
                            db_data['battery'] = battery_lvl
                        if voltage_val is not None:
                            db_data['voltage'] = voltage_val
                        if uptime_val is not None:
                            db_data['uptime'] = uptime_val
                        if packet.get('rxSnr') is not None:
                            db_data['snr'] = packet.get('rxSnr')
                        if packet.get('rxRssi') is not None:
                            db_data['rssi'] = packet.get('rxRssi')
                        if db_data:
                            db.create_node_if_not_exists(from_node_id)
                            db.update_node(from_node_id, db_data)
                        
                        if from_node_id in self.node_dict:
                            self.node_dict[from_node_id].update_metadata(db_data)
                    except Exception:
                        pass

                broadcast_event("device_telemetry", {
                    "id": from_node_id,
                    "battery": battery_lvl,
                    "voltage": voltage_val,
                    "channel_util": ch_util,
                    "air_util_tx": air_tx,
                    "uptime_seconds": uptime_val,
                })
                if ch_util is not None or air_tx is not None:
                    broadcast_event("channel_metrics", {
                        "channel_util": ch_util,
                        "air_util_tx": air_tx,
                    })

            # Routing / ACK de paquetes
            routing = decoded.get('routing') if isinstance(decoded, dict) else None
            if isinstance(routing, dict) and routing.get('errorReason') is not None:
                broadcast_event("message_ack", {
                    "dest": packet.get('toId') or str(packet.get('to')),
                    "status": "delivered" if routing.get('errorReason') == 'NONE' else 'error',
                    "error_reason": routing.get('errorReason'),
                })
        except Exception as e:
            log_p(f"Error procesando on_receive_data: {e}", level="DEBUG")

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

    def send (self, msg, dest=None, channel=0, reply_id=None):
        """
        Envía un mensaje a un destino específico o al canal público

        Args:
            msg (str): Mensaje a enviar
            dest (int|str|None): Destino del mensaje. Puede ser:
                - None o "^all": Mensaje al canal público (broadcast)
                - int: ID numérico del nodo (mensaje directo)
                - str: ID en formato "!xxxxxxxx" (mensaje directo)
            channel (int): Número del canal (0-7). Por defecto 0 (canal primario)
            reply_id (int|None): ID del paquete original al que se responde (in-reply-to)

        Returns:
            bool: True si se envió correctamente, False en caso contrario
        """
        if not self.interface:
            log_p("❌ Error: No hay interfaz conectada")
            return False

        try:
            # Mensaje al canal público (broadcast)
            if dest is None or dest == "^all":
                log_p(
                    f"📢 Enviando mensaje al canal público (canal {channel}): {msg}")
                kwargs = {
                    'text': msg,
                    'channelIndex': channel,
                }
                if reply_id is not None:
                    try:
                        kwargs['replyId'] = int(reply_id)
                    except (ValueError, TypeError):
                        pass
                try:
                    self.interface.sendText(**kwargs)
                except TypeError:
                    kwargs.pop('replyId', None)
                    self.interface.sendText(**kwargs)

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

                kwargs = {
                    'text': msg,
                    'destinationId': dest_str,
                    'channelIndex': channel,
                }
                if reply_id is not None:
                    try:
                        kwargs['replyId'] = int(reply_id)
                    except (ValueError, TypeError):
                        pass
                try:
                    self.interface.sendText(**kwargs)
                except TypeError:
                    kwargs.pop('replyId', None)
                    self.interface.sendText(**kwargs)

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
        metadata = metadata or {}
        is_direct = metadata.get('is_direct', False)
        channel = metadata.get('channel', 0)
        reply_id = metadata.get('reply_id') or metadata.get('id')

        if is_direct:
            # Responder en privado al remitente
            node_from = metadata.get('node_from')
            if isinstance(node_from, dict):
                from_id = node_from.get('id')
            else:
                from_id = str(node_from or '')
            log_p(f"Respondiendo en privado al nodo {from_id}")
            return self.send(msg, dest=from_id, channel=channel, reply_id=reply_id)
        else:
            # Responder en el mismo canal
            log_p(f"↩️ Respondiendo en el canal {channel}")
            return self.send(msg, dest="^all", channel=channel, reply_id=reply_id)

    def request_node_info(self, destination_id: str) -> bool:
        """Solicita NodeInfo a un nodo remoto a través de la radio Meshtastic."""
        if not self.interface:
            log_p("No se puede solicitar NodeInfo: interfaz serie no inicializada", level="WARN")
            return False

        log_p(f"Solicitando NodeInfo al nodo {destination_id}...")
        try:
            dest_val = destination_id
            if hasattr(self.interface, 'sendNodeInfo'):
                self.interface.sendNodeInfo(destinationId=dest_val)
                return True
            elif hasattr(self.interface, 'requestNodeInfo'):
                self.interface.requestNodeInfo(destinationId=dest_val)
                return True
            elif hasattr(self.interface, 'sendData'):
                # Enviar petición a puerto NODEINFO_APP si los helpers directos no existen
                from meshtastic import portnums_pb2
                port = portnums_pb2.PortNum.NODEINFO_APP if hasattr(portnums_pb2, 'PortNum') else 4
                self.interface.sendData(b"", destinationId=dest_val, portNum=port, wantAck=True)
                return True
            else:
                log_p(f"Métodos de requestNodeInfo no disponibles en la versión actual de meshtastic", level="DEBUG")
                return False
        except (Exception, SystemExit) as e:
            log_p(f"Error al solicitar NodeInfo a {destination_id}: {e}", level="WARN")
            return False

    def on_receive_nodeinfo (self, packet, interface):
        """
        TODO: Revisar si entra en este evento, parece que no
        """

        log_p(f"NodeInfo recibido: {packet}")
        pass

    def on_node_update (self, node, interface):
        """Callback reactivo cuando Meshtastic actualiza cualquier nodo en memoria (telemetría, user, posición)."""
        try:
            if not isinstance(node, dict):
                return
            user = node.get('user') or {}
            node_id = user.get('id')
            if not node_id and node.get('num') is not None:
                try:
                    node_id = f"!{int(node['num']):08x}"
                except Exception:
                    pass

            if not node_id:
                return

            fromNodeInfo = self.node_dict.get(node_id)
            if not fromNodeInfo:
                fromNodeInfo = Node(node_id)
                self.node_dict[node_id] = fromNodeInfo

            fromNodeInfo.update_metadata(node)
            log_p(f"Nodo reactivo actualizado: {fromNodeInfo.name} ({node_id})", level="DEBUG")

            try:
                from Models.EventBroadcaster import broadcast_event
                broadcast_event("node_updated", {
                    "id": node_id,
                    "num": node.get('num'),
                    "name": fromNodeInfo.name,
                    "short_name": fromNodeInfo.short_name,
                    "role": fromNodeInfo.role,
                    "snr": fromNodeInfo.snr,
                    "rssi": fromNodeInfo.rssi,
                    "hops": fromNodeInfo.hops,
                    "battery": fromNodeInfo.battery,
                    "voltage": fromNodeInfo.voltage,
                    "last_heard": fromNodeInfo.last_heard,
                })

                # Telemetría de canal si está presente en el nodo
                dev_m = node.get('deviceMetrics') or node.get('device_metrics') or {}
                if isinstance(dev_m, dict):
                    ch_u = dev_m.get('channelUtilization') if dev_m.get('channelUtilization') is not None else dev_m.get('channel_utilization')
                    a_tx = dev_m.get('airUtilTx') if dev_m.get('airUtilTx') is not None else dev_m.get('air_util_tx')
                    if ch_u is not None or a_tx is not None:
                        broadcast_event("channel_metrics", {
                            "channel_util": ch_u,
                            "air_util_tx": a_tx,
                        })
            except Exception:
                pass
        except Exception as e:
            log_p(f"Error en on_node_update: {e}", level="WARN")


    def on_connection (self, interface):
        """
        Procesa el evento al conectarse al dispositivo Meshtastic

        Args:
            interface: La interfaz de meshtastic que se ha conectado
        """
        log_p("Conexión establecida con el dispositivo Meshtastic")
        self.get_nodes()
        try:
            from Models.EventBroadcaster import broadcast_event
            my_info = getattr(interface, 'myInfo', None)
            my_num = getattr(my_info, 'my_node_num', None)
            if my_num:
                my_id = f"!{my_num:08x}"
                local_node = getattr(interface, 'nodes', {}).get(my_id) or getattr(interface, 'nodesByNum', {}).get(my_num) or {}
                user = local_node.get('user', {}) if isinstance(local_node, dict) else {}
                broadcast_event("local_node_info", {
                    "my_node_id": user.get('id') or my_id,
                    "my_num": my_num,
                    "name": user.get('longName'),
                    "short_name": user.get('shortName'),
                    "hw_model": user.get('hwModel'),
                    "region": str(getattr(my_info, 'region', None) or ''),
                })

                # Métricas de canal iniciales del nodo local
                dev_m = local_node.get('deviceMetrics') or local_node.get('device_metrics') or {}
                if isinstance(dev_m, dict):
                    ch_u = dev_m.get('channelUtilization') if dev_m.get('channelUtilization') is not None else dev_m.get('channel_utilization')
                    a_tx = dev_m.get('airUtilTx') if dev_m.get('airUtilTx') is not None else dev_m.get('air_util_tx')
                    if ch_u is not None or a_tx is not None:
                        broadcast_event("channel_metrics", {
                            "channel_util": ch_u,
                            "air_util_tx": a_tx,
                        })
        except Exception:
            pass

    def get_local_hop_limit(self) -> int:
        """Obtiene el límite de saltos (hop_limit) configurado en el firmware del nodo local.

        Si no se puede leer dinámicamente, recurre a env.MESH_DEFAULT_HOP_LIMIT (3 por defecto).
        """
        try:
            if self.interface:
                # 1. Intentar desde localNode.localConfig.lora.hop_limit
                local_node = getattr(self.interface, 'localNode', None)
                if local_node:
                    cfg = getattr(local_node, 'localConfig', None)
                    lora = getattr(cfg, 'lora', None) if cfg else None
                    if lora and getattr(lora, 'hop_limit', None):
                        hl = int(lora.hop_limit)
                        if hl > 0:
                            return hl

                # 2. Intentar desde getNode('^local')
                get_node_fn = getattr(self.interface, 'getNode', None)
                if callable(get_node_fn):
                    node_obj = get_node_fn('^local')
                    if node_obj:
                        cfg = getattr(node_obj, 'localConfig', None)
                        lora = getattr(cfg, 'lora', None) if cfg else None
                        if lora and getattr(lora, 'hop_limit', None):
                            hl = int(lora.hop_limit)
                            if hl > 0:
                                return hl
        except Exception:
            pass

        import env
        return int(getattr(env, 'MESH_DEFAULT_HOP_LIMIT', 3) or 3)

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

        # Configurar un timeout ágil en la librería (por defecto 15s) para no bloquear
        # 20 minutos (300s x waitFactor) si el nodo está inalcanzable u offline.
        orig_expire = getattr(getattr(self.interface, '_timeout', None), 'expireTimeout', 300)
        if hasattr(self.interface, '_timeout'):
            try:
                self.interface._timeout.expireTimeout = int(timeout)
            except Exception:
                pass

        # Normalizar node_id si es un nombre corto o alias
        target_id = node_id
        if not target_id.startswith('!') and not target_id.isdigit():
            try:
                from Models.Database import Database
                found = Database().get_node_by_identifier(target_id) or Database().get_node_by_short_name(target_id)
                if found and found.get('node_id'):
                    target_id = found['node_id']
            except Exception:
                pass

        def _is_timeout_error(err: Exception) -> bool:
            msg = str(err).lower()
            return "timed out" in msg or "timeout" in msg

        try:
            # Intentar variantes en orden de máxima compatibilidad (posicionales primero)
            tried: list[str] = []
            called = False

            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                # 1) Firma estándar meshtastic (dest, hopLimit, channelIndex)
                try:
                    send_fn(dest=target_id, hopLimit=3, channelIndex=0)
                    called = True
                except (TypeError, SystemExit, Exception) as e:
                    if _is_timeout_error(e):
                        raise TimeoutError(f"Timed out waiting for traceroute to {target_id}") from e
                    tried.append(str(e))

            # 2) Posicional estándar (target_id, 3, 0)
            if not called:
                try:
                    send_fn(target_id, 3, 0)
                    called = True
                except (TypeError, SystemExit, Exception) as e:
                    if _is_timeout_error(e):
                        raise TimeoutError(f"Timed out waiting for traceroute to {target_id}") from e
                    tried.append(str(e))

            # 3) Posicional con callback
            if not called:
                try:
                    send_fn(target_id, 3, 0, _on_response)
                    called = True
                except (TypeError, SystemExit, Exception) as e:
                    if _is_timeout_error(e):
                        raise TimeoutError(f"Timed out waiting for traceroute to {target_id}") from e
                    tried.append(str(e))

            # 4) Posicional con callback como segundo argumento
            if not called:
                try:
                    send_fn(target_id, _on_response)
                    called = True
                except (TypeError, SystemExit, Exception) as e:
                    if _is_timeout_error(e):
                        raise TimeoutError(f"Timed out waiting for traceroute to {target_id}") from e
                    tried.append(str(e))

            # 5) Posicional solo id
            if not called:
                try:
                    send_fn(target_id)
                    called = True
                except (TypeError, SystemExit, Exception) as e:
                    if _is_timeout_error(e):
                        raise TimeoutError(f"Timed out waiting for traceroute to {target_id}") from e
                    tried.append(str(e))

            # 6) Keywords alternativas
            if not called:
                try:
                    send_fn(destinationId=target_id, onResponse=_on_response)
                    called = True
                except (TypeError, SystemExit, Exception) as e:
                    if _is_timeout_error(e):
                        raise TimeoutError(f"Timed out waiting for traceroute to {target_id}") from e
                    tried.append(str(e))
                    try:
                        send_fn(id=target_id, onResponse=_on_response)
                        called = True
                    except (TypeError, SystemExit, Exception) as e2:
                        if _is_timeout_error(e2):
                            raise TimeoutError(f"Timed out waiting for traceroute to {target_id}") from e2
                        tried.append(str(e2))

            # 7) Último recurso: keyword mínima sin callback
            if not called:
                try:
                    send_fn(destinationId=target_id)
                    called = True
                except (Exception, SystemExit) as e:
                    if _is_timeout_error(e):
                        raise TimeoutError(f"Timed out waiting for traceroute to {target_id}") from e
                    tried.append(str(e))

            if not called:
                # Dejar la salida capturada hasta ahora y lanzar error
                text_now = (buf_out.getvalue() or '') + (buf_err.getvalue() or '')
                raise TypeError("sendTraceRoute no pudo ser invocado de forma compatible; errores: " + " | ".join(tried) + f"\n{text_now}")

            # Ventana de espera para que se impriman las rutas
            start = time.time()
            last_len = 0
            while time.time() - start < timeout:
                # Si el callback recibe algo, reseteamos el contador para
                # volver a esperar 'timeout' completo desde la última actividad
                # (de lo contrario los sleep extra no prolongan la ventana real).
                if len(results) != last_len:
                    last_len = len(results)
                    start = time.time()
                    time.sleep(0.3)
                time.sleep(0.2)
        finally:
            if hasattr(self.interface, '_timeout'):
                try:
                    self.interface._timeout.expireTimeout = orig_expire
                except Exception:
                    pass

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
                            m = re.search(r'(!?[0-9a-fA-F]{6,8}|![0-9a-fA-F]+)', part)
                            if m:
                                node = m.group(1)
                                if not node.startswith('!'):
                                    node = '!' + node
                            else:
                                node = None
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
                            m = re.search(r'(!?[0-9a-fA-F]{6,8}|![0-9a-fA-F]+)', part)
                            if m:
                                node = m.group(1)
                                if not node.startswith('!'):
                                    node = '!' + node
                            else:
                                node = None
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
                user = node_info.get('user', {})
                id = user.get('id')
                if not id and node_num:
                    try:
                        id = f"!{int(node_num):08x}"
                    except Exception:
                        id = None
                
                if not id or str(id).strip() in ("", "None", "null", "Desconocido"):
                    continue

                id = str(id).strip()
                newNodeInfo = Node(id)

                newNodeInfo.update_metadata({
                    "name": user.get('longName', None),
                    "num": node_num,
                    "short_name": user.get('shortName', None),
                    "mac_addr": user.get('macaddr', None),
                    "hw_model": user.get('hwModel', None),
                    "role": user.get('role', None),

                    "snr": node_info.get('snr', None),
                    "last_heard": node_info.get('lastHeard', None),
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
                from_id = packet.get('fromId')
                if not from_id and packet.get('from'):
                    try:
                        from_id = f"!{int(packet['from']):08x}"
                    except Exception:
                        from_id = None
                
                if not from_id or str(from_id).strip() in ("", "None", "null", "Desconocido"):
                    from_id = None

                to_id = packet.get('toId', '^all')
                to_num = packet.get('to', 0xFFFFFFFF)

                if to_id == '^all' or to_num == 0xFFFFFFFF:
                    is_direct = False
                else:
                    is_direct = True

                # Pedir info del nodo que envía
                fromNodeInfo = self.node_dict.get(from_id, None) if from_id else None

                if from_id and not fromNodeInfo:
                    fromNodeInfo = Node(from_id)
                    self.node_dict[from_id] = fromNodeInfo

                # Comprobar vigilancia y descarte de ignorados
                try:
                    from Models.MeshWatcher import MeshWatcher
                    if MeshWatcher.inspect_packet(packet, fromNodeInfo):
                        return
                except Exception:
                    pass

                if fromNodeInfo:
                    fromNodeInfo.update_metadata({
                        "num": packet.get('from', None),
                        "snr": packet.get('rxSnr', None),
                        "rssi": packet.get('rxRssi', None),
                        "hop_limit": packet.get('hopLimit', None),
                        "hop_start": packet.get('hopStart', None),
                        "is_direct": is_direct,
                        "via_mqtt": packet.get('viaMqtt', False),
                    })


                metadata = {
                    "id": packet.get('id'),
                    "reply_id": packet.get('id'),
                    "node_from": fromNodeInfo.get_metadata(),
                    "node_to": {
                        "id": to_id,
                        "num": packet.get('to', 'N/A'),
                    },
                    "channel": packet.get('channel', 0),
                    "is_direct": is_direct,
                    "rx_snr": fromNodeInfo.snr,
                    "rx_rssi": fromNodeInfo.rssi,
                    "via_mqtt": fromNodeInfo.via_mqtt,
                }

                # Emitir evento en tiempo real a la pasarela WiFi (IPC no bloqueante, en RAM)
                try:
                    from Models.EventBroadcaster import broadcast_event
                    broadcast_event("message_rx", {
                        "from": from_id,
                        "from_name": fromNodeInfo.name,
                        "from_short_name": fromNodeInfo.short_name,
                        "to": to_id,
                        "channel": packet.get('channel', 0),
                        "text": msg,
                        "snr": fromNodeInfo.snr,
                        "rssi": fromNodeInfo.rssi,
                        "hops": fromNodeInfo.hops,
                        "is_direct": is_direct,
                        "via_mqtt": fromNodeInfo.via_mqtt,
                    })
                except Exception:
                    pass

                # Busco comando y argumentos en el mensaje
                command, cmd_args = search_command(msg)

                # Si el mensaje recibido es un comando, evaluar si se ejecuta la respuesta
                if command:
                    # Control de saturación y lista negra de nodos (Módulo 06)
                    try:
                        from Models.AntiAbuse import anti_abuse_manager
                        node_name = fromNodeInfo.name if fromNodeInfo else None
                        allowed, ban_reason = anti_abuse_manager.is_allowed(from_id, command=command, node_name=node_name)
                        if not allowed:
                            return
                    except Exception as e:
                        log_p(f"[AntiAbuse] Error en verificación: {e}", level="WARN")

                    # Directo responde siempre, en grupo solo a ciertos comandos
                    if not is_direct and not self.command_dict[command]['in_group']:
                        return

                    # Filtro de saltos (Hops): si el paquete vino por RF (no MQTT), comprobar distancia
                    if not fromNodeInfo.via_mqtt:
                        sender_hops = None
                        h_start = packet.get('hopStart')
                        h_limit = packet.get('hopLimit')
                        if h_start is not None and h_limit is not None:
                            try:
                                sender_hops = max(0, int(h_start) - int(h_limit))
                            except Exception:
                                sender_hops = None
                        elif fromNodeInfo.hops is not None:
                            sender_hops = int(fromNodeInfo.hops)

                        if sender_hops is not None:
                            local_hop_limit = self.get_local_hop_limit()
                            max_allowed_hops = local_hop_limit + 1
                            if sender_hops > max_allowed_hops:
                                log_p(
                                    f"[comando] Omitida respuesta a '{command}' de {from_id} por exceso de saltos "
                                    f"({sender_hops} saltos > máx permitido {max_allowed_hops} [local {local_hop_limit}+1])",
                                    level="INFO",
                                )
                                return

                    self.command_dict[command]["callback"](self,
                                                           cmd_args, msg,
                                                           metadata)

                    # Registro centralizado del comando en histórico
                    # (commands_sent). Se hace aquí, tras ejecutar el callback,
                    # para no duplicar esta lógica en cada Commands/*.py.
                    try:
                        from Models.Database import Database
                        node_id = (metadata.get('node_from') or {}).get('id')
                        message_tail = ' '.join(cmd_args) if cmd_args else None
                        Database().log_command(
                            node_id=node_id,
                            command=command,
                            message=message_tail,
                            parameters=None,
                        )
                    except Exception as e:
                        log_p(f"Error registrando comando: {e}", level="WARN")

        except Exception as e:
            log_p(f"Error procesando paquete: {e}")