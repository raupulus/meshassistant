from __future__ import annotations

import unittest
from unittest.mock import MagicMock
from Models.SerialInterface import SerialInterface
from Models.Database import Database
import env


class DummyLoraConfig:
    def __init__(self, hop_limit: int = 4):
        self.hop_limit = hop_limit


class DummyLocalConfig:
    def __init__(self, hop_limit: int = 4):
        self.lora = DummyLoraConfig(hop_limit)


class DummyLocalNode:
    def __init__(self, hop_limit: int = 4):
        self.localConfig = DummyLocalConfig(hop_limit)


class DummyInterface:
    def __init__(self, hop_limit: int = 4):
        self.localNode = DummyLocalNode(hop_limit)
        self.myInfo = MagicMock(my_node_num=12345)
        self.nodes = {}
        self.nodesByNum = {}

    def sendText(self, text, destinationId=None, channelIndex=0):
        pass


class TestHopsFilter(unittest.TestCase):

    def setUp(self):
        self.serial_iface = SerialInterface("/dev/null")
        self.serial_iface.interface = DummyInterface(hop_limit=4)
        self.executed_commands = []

        def dummy_cmd_callback(interface, args, msg, metadata):
            self.executed_commands.append({
                "args": args,
                "msg": msg,
                "metadata": metadata,
            })

        self.serial_iface.command_dict = {
            "ping": {
                "callback": dummy_cmd_callback,
                "in_group": True,
                "usage": "/ping",
                "info": "Prueba ping",
            }
        }

    def _create_text_packet(self, text: str, hop_start: int = 3, hop_limit: int = 3, via_mqtt: bool = False, from_id: str = "!testnode"):
        return {
            "fromId": from_id,
            "toId": "^all",
            "from": 999999,
            "to": 0xFFFFFFFF,
            "channel": 0,
            "hopStart": hop_start,
            "hopLimit": hop_limit,
            "viaMqtt": via_mqtt,
            "rxSnr": 10.0,
            "rxRssi": -80,
            "decoded": {
                "portnum": "TEXT_MESSAGE_APP",
                "text": text,
            },
        }

    def test_get_local_hop_limit_dynamic(self):
        # 1. Leer dinámicamente del firmware mockeado
        self.assertEqual(self.serial_iface.get_local_hop_limit(), 4)

        # 2. Si cambia en caliente en el firmware a 5
        self.serial_iface.interface.localNode.localConfig.lora.hop_limit = 5
        self.assertEqual(self.serial_iface.get_local_hop_limit(), 5)

        # 3. Si no hay interfaz conectada, recurrir al default
        self.serial_iface.interface = None
        orig_default = getattr(env, 'MESH_DEFAULT_HOP_LIMIT', 3)
        try:
            env.MESH_DEFAULT_HOP_LIMIT = 3
            self.assertEqual(self.serial_iface.get_local_hop_limit(), 3)
        finally:
            env.MESH_DEFAULT_HOP_LIMIT = orig_default

    def test_command_executed_within_hop_limit_plus_one(self):
        # local_hop_limit = 4, max_allowed = 5
        self.serial_iface.interface = DummyInterface(hop_limit=4)

        # Caso 1: 0 saltos (directo, hopStart=3, hopLimit=3)
        pkt_0_hops = self._create_text_packet("/ping", hop_start=3, hop_limit=3, from_id="!node0")
        self.serial_iface.on_receive_text(pkt_0_hops, self.serial_iface.interface)
        self.assertEqual(len(self.executed_commands), 1)

        # Caso 2: 4 saltos (hopStart=4, hopLimit=0)
        pkt_4_hops = self._create_text_packet("/ping", hop_start=4, hop_limit=0, from_id="!node4")
        self.serial_iface.on_receive_text(pkt_4_hops, self.serial_iface.interface)
        self.assertEqual(len(self.executed_commands), 2)

        # Caso 3: 5 saltos (hopStart=7, hopLimit=2, exacto local + 1) -> PERMITIDO
        pkt_5_hops = self._create_text_packet("/ping", hop_start=7, hop_limit=2, from_id="!node5")
        self.serial_iface.on_receive_text(pkt_5_hops, self.serial_iface.interface)
        self.assertEqual(len(self.executed_commands), 3)

    def test_command_blocked_when_exceeding_hop_limit_plus_one(self):
        # local_hop_limit = 4, max_allowed = 5
        self.serial_iface.interface = DummyInterface(hop_limit=4)

        # Caso 4: 6 saltos (hopStart=7, hopLimit=1, excede local+1) -> BLOQUEADO
        pkt_6_hops = self._create_text_packet("/ping", hop_start=7, hop_limit=1, from_id="!node6")
        self.serial_iface.on_receive_text(pkt_6_hops, self.serial_iface.interface)
        self.assertEqual(len(self.executed_commands), 0, "No debe ejecutar comando si supera max saltos")

        # Verificar que aunque se omita el comando, el nodo SÍ se registra/actualiza en memoria
        self.assertIn("!node6", self.serial_iface.node_dict)
        self.assertEqual(self.serial_iface.node_dict["!node6"].hops, 6)

        # Caso 5: 7 saltos -> BLOQUEADO
        pkt_7_hops = self._create_text_packet("/ping", hop_start=7, hop_limit=0, from_id="!node7")
        self.serial_iface.on_receive_text(pkt_7_hops, self.serial_iface.interface)
        self.assertEqual(len(self.executed_commands), 0)

    def test_mqtt_packets_bypass_hops_filter(self):
        # local_hop_limit = 4
        self.serial_iface.interface = DummyInterface(hop_limit=4)

        # Paquete a 6 saltos pero via MQTT -> DEBE EJECUTARSE
        pkt_mqtt = self._create_text_packet("/ping", hop_start=7, hop_limit=1, via_mqtt=True, from_id="!nodemqtt")
        self.serial_iface.on_receive_text(pkt_mqtt, self.serial_iface.interface)
        self.assertEqual(len(self.executed_commands), 1, "Mensajes MQTT deben responder sin limitación LoRa")


if __name__ == '__main__':
    unittest.main()
