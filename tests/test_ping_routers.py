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
        db.create_node_if_not_exists("!testrouter1")
        db.update_node("!testrouter1", {
            "name": "Router Cerro",
            "short_name": "RCER",
            "role": 2, # ROUTER
            "snr": 9.5,
            "hops": 1,
        })
        routers = db.get_router_nodes(["RCER"])
        self.assertTrue(any(r.get("short_name") == "RCER" for r in routers))


if __name__ == '__main__':
    unittest.main()
