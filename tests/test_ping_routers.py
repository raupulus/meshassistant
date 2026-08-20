import unittest
from datetime import datetime
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
        env.ROUTER_NODES = ['RCER', 'INEXISTENTE', 'VIEJO', 'FAR_ROUTER', 'NOTRACE_ROUTER']
        env.ROUTER_MAX_HOPS = 2
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

        # Router lejano (>2 hops) -> debe ser ignorado
        db.create_node_if_not_exists("!farnode")
        db.update_node("!farnode", {
            "name": "Router Lejano",
            "short_name": "FAR_ROUTER",
            "role": 2,
            "hops": 4,
            "last_heard": int(datetime.now().timestamp()),
        })

        # Router cercano sin trace -> debe mostrarse sin SNR falso de la base
        db.create_node_if_not_exists("!notracenode")
        db.update_node("!notracenode", {
            "name": "Router Sin Trace",
            "short_name": "NOTRACE_ROUTER",
            "role": 2,
            "hops": 1,
            "snr": 12.2, # SNR local con la base
            "last_heard": int(datetime.now().timestamp()),
        })

        routers_callback(mock, [], '/routers', meta)
        self.assertGreaterEqual(len(mock.replies), 1)
        full_text = " ".join(mock.replies)
        # Verifica corchetes y formato
        self.assertIn("[RCER:", full_text)
        self.assertIn("[INEXISTENTE | offline]", full_text)
        self.assertIn("[VIEJO | offline]", full_text, "Router no escuchado en 24h debe marcarse offline")
        self.assertNotIn("FAR_ROUTER", full_text, "Routers con más de 2 hops deben excluirse del informe")
        self.assertIn("[NOTRACE_ROUTER:", full_text)
        self.assertNotIn("[NOTRACE_ROUTER: 0s - 0 hops(12.2dB)]", full_text, "No debe mostrar el SNR local de la base si no hay trace")

    def test_trace_snr_and_router_prioritization(self):
        db = Database()
        # 1. Crear nodo router y guardar trace con SNR real de enlace exterior
        db.create_node_if_not_exists("!cadiz13_test")
        db.update_node("!cadiz13_test", {
            "name": "Router Cadiz Test 13",
            "short_name": "CA13T",
            "role": 2, # ROUTER
            "snr": 12.5, # SNR local con la base
            "hops": 1,
        })
        # Insertar trace
        trace_id = db.enqueue_trace("!cadiz13_test")
        db.mark_trace_done_with_route(
            trace_id,
            True,
            text="Route traced towards destination: !bot --> !base (12.0 dB) --> !cadiz13_test (4.5 dB)",
            to_name="Router Cadiz Test 13",
            to_name_short="CA13T",
            hops=[
                {'id': '!base', 'name_short': 'RAU0', 'snr': 12.0},
                {'id': '!cadiz13_test', 'name_short': 'CA13T', 'snr': 4.5},
            ],
            return_hops=[
                {'id': '!base', 'name_short': 'RAU0', 'snr': 5.2},
                {'id': '!bot', 'name_short': 'BOT', 'snr': 12.2},
            ]
        )

        # get_latest_trace_snr debe devolver el SNR del enlace exterior (5.2 dB o 4.5 dB), no el del bot (12.2 dB)
        snr = db.get_latest_trace_snr("!cadiz13_test", ["RAU0", "!base"])
        self.assertIsNotNone(snr)
        self.assertEqual(snr, 5.2)

        # 2. Priorización de traces: un router sin traza reciente (≥6h) debe tener prioridad sobre un cliente normal
        import time
        uniq_id = int(time.time())
        r_node_id = f"!r_{uniq_id}"
        c_node_id = f"!c_{uniq_id}"

        db.create_node_if_not_exists(r_node_id)
        db.update_node(r_node_id, {
            "name": "Fresh Router",
            "short_name": f"R{uniq_id % 1000}",
            "role": 2, # ROUTER
            "hops": 1,
        })
        db.create_node_if_not_exists(c_node_id)
        db.update_node(c_node_id, {
            "name": "Fresh Client",
            "short_name": f"C{uniq_id % 1000}",
            "role": 0,
            "hops": 1,
        })

        # get_next_node_to_trace debe devolver el router prioritario (prioridad 1)
        next_to_trace = db.get_next_node_to_trace(
            hops_limit=2,
            reload_hours=72,
            router_reload_hours=6,
            router_identifiers=[f"R{uniq_id % 1000}"],
        )
        # El resultado debe ser un router que necesita trace (nunca el cliente recién creado)
        self.assertNotEqual(next_to_trace, c_node_id)

        # Si marcamos todos los routers existentes como trazados recientemente (<6h)
        for r in db.get_router_nodes([f"R{uniq_id % 1000}", "RPRI", "RCER", "RMON", "VIEJO", "CA13T", "CA12", "CA13", "CA01", "CA02", "CA03", "CA04", "CA05", "CA16", "CA23", "RAU0"]):
            nid = r.get('node_id')
            if nid:
                t_id = db.enqueue_trace(nid)
                db.mark_trace_done_with_route(t_id, True, text="done", hops=[], return_hops=[])

        # Ahora que todos los routers están trazados (<6h), debe elegir un nodo cliente elegible
        next_node = db.get_next_node_to_trace(
            hops_limit=2,
            reload_hours=72,
            router_reload_hours=6,
            router_identifiers=[f"R{uniq_id % 1000}"],
        )
        self.assertIsNotNone(next_node)


if __name__ == '__main__':
    unittest.main()
