import unittest
import tempfile
import time
import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from create_db import ensure_database
from Models.Database import Database
from Models.SerialInterface import SerialInterface
from Services.Gateway import GatewayService


class TestDashboard(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_dashboard.sql"
        ensure_database(self.db_path)
        self.db = Database(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_dashboard_metrics_empty_db(self):
        """Valida que get_dashboard_metrics funcione sin errores en una base de datos vacía."""
        metrics = self.db.get_dashboard_metrics()
        self.assertIn("nodes", metrics)
        self.assertIn("snr", metrics)
        self.assertIn("roles", metrics)
        self.assertIn("activity_24h", metrics)
        self.assertIn("hourly_activity", metrics)
        self.assertIn("recent_nodes", metrics)
        self.assertIn("stats", metrics)

        # Nodos
        self.assertEqual(metrics["nodes"]["total"], 0)
        self.assertEqual(metrics["nodes"]["rf"], 0)
        self.assertEqual(metrics["nodes"]["mqtt"], 0)
        self.assertEqual(metrics["nodes"]["active_24h"], 0)

        # SNR
        self.assertIsNone(metrics["snr"]["avg"])
        self.assertEqual(metrics["snr"]["count"], 0)
        self.assertEqual(metrics["snr"]["excellent"], 0)

        # Actividad 24h
        self.assertEqual(len(metrics["activity_24h"]), 24)
        for h in metrics["activity_24h"]:
            self.assertEqual(h["total"], 0)

    def test_get_dashboard_metrics_with_data(self):
        """Valida la agregación correcta de métricas de nodos, SNR, roles y actividad 24h."""
        now = int(time.time())

        # Insertar nodos: 2 RF (uno reciente excelente SNR, uno antiguo regular SNR), 1 MQTT
        self.db.create_node_if_not_exists("!11111111", {
            "num": 286331153,
            "name": "Nodo RF 1",
            "short_name": "RF1",
            "hw_model": "TBEAM",
            "role": "CLIENT",
            "snr": 8.5,
            "battery": 95,
            "via_mqtt": 0,
            "last_heard": now - 60,
        })
        self.db.create_node_if_not_exists("!22222222", {
            "num": 572662306,
            "name": "Nodo RF 2",
            "short_name": "RF2",
            "hw_model": "HELTEC_V3",
            "role": "ROUTER",
            "snr": -2.0,
            "battery": 60,
            "via_mqtt": 0,
            "last_heard": now - 7200,
        })
        self.db.create_node_if_not_exists("!33333333", {
            "num": 858993459,
            "name": "Nodo MQTT 1",
            "short_name": "MQ1",
            "hw_model": "LINUX",
            "role": "CLIENT",
            "snr": None,
            "via_mqtt": 1,
            "last_heard": now - 300,
        })

        # Insertar actividad reciente (traces, commands_sent)
        self.db.enqueue_trace("!11111111")
        self.db.log_command(node_id="!11111111", command="/ping", message="pong")

        metrics = self.db.get_dashboard_metrics()

        # Nodos
        self.assertEqual(metrics["nodes"]["total"], 3)
        self.assertEqual(metrics["nodes"]["rf"], 2)
        self.assertEqual(metrics["nodes"]["mqtt"], 1)
        self.assertEqual(metrics["nodes"]["active_1h"], 2)
        self.assertEqual(metrics["nodes"]["active_24h"], 3)

        # SNR (solo nodos RF: 8.5 y -2.0 -> avg = 3.2)
        self.assertEqual(metrics["snr"]["count"], 2)
        self.assertAlmostEqual(metrics["snr"]["avg"], 3.2, places=1)
        self.assertEqual(metrics["snr"]["excellent"], 1)
        self.assertEqual(metrics["snr"]["fair"], 1)
        self.assertEqual(metrics["snr"]["good"], 0)
        self.assertEqual(metrics["snr"]["poor"], 0)

        # Roles
        self.assertEqual(metrics["roles"].get("CLIENT"), 2)
        self.assertEqual(metrics["roles"].get("ROUTER"), 1)

        # Actividad
        total_24h = sum(h["total"] for h in metrics["activity_24h"])
        self.assertGreaterEqual(total_24h, 2)

        # Nodos recientes
        self.assertGreaterEqual(len(metrics["recent_nodes"]), 1)
        self.assertEqual(metrics["recent_nodes"][0]["node_id"], "!11111111")

    def test_serial_broadcast_methods_mocked(self):
        """Valida que los métodos broadcast de SerialInterface emitan correctamente hacia ^all sin enviar radio real."""
        interface = SerialInterface(serial_port="/dev/null")
        interface.interface = MagicMock()
        interface.local_node = MagicMock()

        # 1. announce_node_info
        res1 = interface.announce_node_info("^all")
        self.assertTrue(res1)
        interface.interface.sendNodeInfo.assert_called_with(destinationId="^all")

        # 2. announce_position
        res2 = interface.announce_position("^all", channel_index=0)
        self.assertTrue(res2)
        interface.interface.sendPosition.assert_called_with(destinationId="^all", wantAck=False, wantResponse=False, channelIndex=0)

        # 3. request_position
        res3 = interface.request_position("^all", channel_index=0, want_response=True)
        self.assertTrue(res3)
        interface.interface.sendData.assert_called()

        # 4. request_node_info con ^all
        res4 = interface.request_node_info("^all")
        self.assertTrue(res4)

    def test_gateway_broadcast_action_cooldown(self):
        """Valida la pasarela Gateway: encolado de broadcast y rate limiting/cooldown estricto."""
        gateway = GatewayService(port=8689)
        gateway.db = self.db
        dummy_ws = MagicMock()

        # Petición 1: announce_nodeinfo (permitida)
        resp1 = asyncio.run(gateway._handle_action(dummy_ws, {"action": "broadcast_action", "params": {"action_type": "announce_nodeinfo", "channel": 0}}))
        self.assertTrue(resp1.get("success"))
        self.assertEqual(resp1.get("data", {}).get("action_type"), "announce_nodeinfo")
        self.assertEqual(resp1.get("data", {}).get("cooldown_seconds"), 60)

        # Verificar que se encoló en outbox
        pending = self.db.get_next_pending_outbox()
        self.assertIsNotNone(pending)
        self.assertEqual(pending["text"], "__ANNOUNCE_NODEINFO__")
        self.assertEqual(pending["dest"], "^all")

        # Petición 2 inmediata: announce_nodeinfo (rechazada por rate limiting)
        resp2 = asyncio.run(gateway._handle_action(dummy_ws, {"action": "broadcast_action", "params": {"action_type": "announce_nodeinfo", "channel": 0}}))
        self.assertFalse(resp2.get("success"))
        self.assertIn("Cooldown activo", resp2.get("error", ""))

        # Petición 3: request_nodeinfo (permitida primera vez)
        resp3 = asyncio.run(gateway._handle_action(dummy_ws, {"action": "broadcast_action", "params": {"action_type": "request_nodeinfo", "channel": 0}}))
        self.assertTrue(resp3.get("success"))
        self.assertEqual(resp3.get("data", {}).get("action_type"), "request_nodeinfo")
        self.assertEqual(resp3.get("data", {}).get("cooldown_seconds"), 120)

        # Petición 4 inmediata: request_nodeinfo (rechazada por cooldown 120s)
        resp4 = asyncio.run(gateway._handle_action(dummy_ws, {"action": "broadcast_action", "params": {"action_type": "request_nodeinfo", "channel": 0}}))
        self.assertFalse(resp4.get("success"))
        self.assertIn("Cooldown activo", resp4.get("error", ""))

        # Petición 5: tipo desconocido
        resp5 = asyncio.run(gateway._handle_action(dummy_ws, {"action": "broadcast_action", "params": {"action_type": "invalid_action"}}))
        self.assertFalse(resp5.get("success"))
        self.assertIn("no válida", resp5.get("error", ""))


if __name__ == "__main__":
    unittest.main()
