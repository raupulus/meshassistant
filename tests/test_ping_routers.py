import unittest
from Commands.ping import ping_callback
from Commands.routers import routers_callback
from Models.Database import Database
import env


class MockInterface:
    def __init__(self):
        self.replies = []
    def reply_to_message(self, text, metadata):
        self.replies.append(text)


class TestPingRouters(unittest.TestCase):

    def setUp(self):
        env.BASE_NODE_SHORT_NAME = 'RAU0'
        env.BASE_NODE_ID = '!875e3787'

    def test_ping_direct_rf_shows_snr(self):
        mock = MockInterface()
        meta = {
            'node_from': {'id': '!1111', 'name': 'DirectNode', 'hops': 0, 'snr': 8.5, 'via_mqtt': False},
            'node_to': {'id': '!bot'},
            'is_direct': True,
        }
        ping_callback(mock, [], '/ping', meta)
        self.assertEqual(len(mock.replies), 1)
        self.assertIn("Pong desde Chipiona", mock.replies[0])
        self.assertIn("SNR: +8.5 dB", mock.replies[0])

    def test_ping_via_base_decrements_hop_and_no_snr(self):
        mock = MockInterface()
        # 1 hop at bot -> 0 hops to base (repeated by RAU0)
        meta = {
            'node_from': {'id': '!2222', 'name': 'RooftopNode', 'hops': 1, 'snr': 12.0, 'via_mqtt': False},
            'node_to': {'id': '!bot'},
            'is_direct': True,
        }
        ping_callback(mock, [], '/ping', meta)
        self.assertEqual(len(mock.replies), 1)
        self.assertEqual(mock.replies[0], "Pong desde Chipiona, 0 hops")
        self.assertNotIn("SNR", mock.replies[0])

    def test_ping_two_hops_decrements_to_one_hop(self):
        mock = MockInterface()
        # 2 hops at bot -> 1 hop to base
        meta = {
            'node_from': {'id': '!3333', 'name': 'FarNode', 'hops': 2, 'snr': 12.0, 'via_mqtt': False},
            'node_to': {'id': '!bot'},
            'is_direct': True,
        }
        ping_callback(mock, [], '/ping', meta)
        self.assertEqual(len(mock.replies), 1)
        self.assertEqual(mock.replies[0], "Pong desde Chipiona, 1 hop")
        self.assertNotIn("SNR", mock.replies[0])

    def test_ping_mqtt(self):
        mock = MockInterface()
        meta = {
            'node_from': {'id': '!4444', 'name': 'MqttNode', 'hops': 0, 'via_mqtt': True},
            'node_to': {'id': '!bot'},
            'is_direct': True,
        }
        ping_callback(mock, [], '/ping', meta)
        self.assertEqual(len(mock.replies), 1)
        self.assertEqual(mock.replies[0], "Pong, via MQTT")

    def test_database_get_router_nodes(self):
        db = Database()
        # 1. Nodo con rol ROUTER real
        db.create_node_if_not_exists("!testrouter1")
        db.update_node("!testrouter1", {
            "name": "Nodo Cerro",
            "short_name": "RCER",
            "role": 2,  # ROUTER
            "snr": 9.5,
            "hops": 1,
        })

        # 2. Nodo con rol REPEATER real
        db.create_node_if_not_exists("!testrouter2")
        db.update_node("!testrouter2", {
            "name": "Repetidor Monte",
            "short_name": "RMON",
            "role": "REPEATER",
            "snr": 11.0,
            "hops": 0,
        })

        # 3. Nodo cliente falso que pone "Router" en su nombre pero role es CLIENT (0)
        db.create_node_if_not_exists("!fakeclient")
        db.update_node("!fakeclient", {
            "name": "Router Falso de Tercero",
            "short_name": "FAKE",
            "role": 0,  # CLIENT
            "snr": 5.0,
            "hops": 2,
        })

        routers = db.get_router_nodes(["RCER"])
        router_shorts = [r.get("short_name") for r in routers]

        self.assertIn("RCER", router_shorts)
        self.assertIn("RMON", router_shorts)
        self.assertNotIn("FAKE", router_shorts, "Nodos con 'router' en el nombre pero sin role de router deben ser ignorados")

    def test_routers_callback_formatting(self):
        mock = MockInterface()
        meta = {'is_direct': True, 'node_from': {'id': '!test'}, 'node_to': {'id': '!bot'}}
        env.ROUTER_NODES = ['RCER', 'INEXISTENTE', 'VIEJO']
        db = Database()
        db.create_node_if_not_exists("!viejonode")
        db.update_node("!viejonode", {
            "name": "Router Antiguo",
            "short_name": "VIEJO",
            "role": 2,
            "snr": 10.0,
            "hops": 1,
            "last_heard": 1000000000, # Año 2001 (>24h)
        })
        routers_callback(mock, [], '/routers', meta)
        self.assertEqual(len(mock.replies), 1)
        # Verifica corchetes y formato
        self.assertIn("[RCER:", mock.replies[0])
        self.assertIn("(9.5dB)]", mock.replies[0])
        self.assertIn("[INEXISTENTE | offline]", mock.replies[0])
        self.assertIn("[VIEJO | offline]", mock.replies[0], "Router no escuchado en 24h debe marcarse offline")


if __name__ == '__main__':
    unittest.main()
