import unittest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from create_db import ensure_database
from Models.Database import Database
from Models.Node import Node
from Models.SerialInterface import SerialInterface


class TestInaTelemetry(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_ina.sql"
        ensure_database(self.db_path)
        self.db = Database(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schema_has_ina_columns(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("PRAGMA table_info(nodes)")
            cols = [r[1] for r in cur.fetchall()]
            self.assertIn("power_ina1", cols)
            self.assertIn("power_ina2", cols)
            self.assertIn("power_ina3", cols)

    def test_database_update_and_get_ina_nodes(self):
        node_id = "!ina_node_01"
        self.db.create_node_if_not_exists(node_id)
        self.db.update_node(node_id, {
            "name": "Nodo Sensor Solar",
            "short_name": "SOLA",
            "battery": 100,
            "voltage": 4.25,
            "power_ina1": 3.75,
            "power_ina2": 4.12,
            "power_ina3": 3.50,
        })

        node_data = self.db.get_node(node_id)
        self.assertIsNotNone(node_data)
        self.assertEqual(node_data.get("power_ina1"), 3.75)
        self.assertEqual(node_data.get("power_ina2"), 4.12)
        self.assertEqual(node_data.get("power_ina3"), 3.50)

        all_nodes = self.db.get_all_nodes()
        found = next((n for n in all_nodes if n.get("node_id") == node_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found.get("power_ina1"), 3.75)
        self.assertEqual(found.get("power_ina2"), 4.12)
        self.assertEqual(found.get("power_ina3"), 3.50)

    def test_node_model_with_ina(self):
        node_id = "!ina_node_02"
        node = Node(node_id)
        node.update_metadata({
            "name": "Router INA",
            "powerMetrics": {
                "ch1Voltage": 3.82,
                "ch2Voltage": 4.05,
                "ch3Voltage": 3.44,
            }
        })
        self.assertEqual(node.power_ina1, 3.82)
        self.assertEqual(node.power_ina2, 4.05)
        self.assertEqual(node.power_ina3, 3.44)

        meta = node.get_metadata()
        self.assertEqual(meta.get("power_ina1"), 3.82)
        self.assertEqual(meta.get("power_ina2"), 4.05)
        self.assertEqual(meta.get("power_ina3"), 3.44)

    @patch("Models.EventBroadcaster.broadcast_event")
    @patch("Models.Database.Database")
    def test_serial_interface_parses_power_metrics(self, mock_db_cls, mock_broadcast):
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db

        interface = SerialInterface(serial_port="/dev/null")
        interface.node_dict = {}

        packet = {
            "fromId": "!ina_node_03",
            "rxSnr": 6.5,
            "rxRssi": -72,
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {
                    "deviceMetrics": {
                        "batteryLevel": 100,
                        "voltage": 4.30,
                    },
                    "powerMetrics": {
                        "ch1_voltage": 3.71,
                        "ch2_voltage": 4.18,
                        "ch3_voltage": 3.52,
                    }
                }
            }
        }

        interface.on_receive_data(packet=packet, interface=interface)

        mock_db.update_node.assert_called()
        call_args = mock_db.update_node.call_args[0]
        self.assertEqual(call_args[0], "!ina_node_03")
        updated_data = call_args[1]
        self.assertEqual(updated_data.get("power_ina1"), 3.71)
        self.assertEqual(updated_data.get("power_ina2"), 4.18)
        self.assertEqual(updated_data.get("power_ina3"), 3.52)

        mock_broadcast.assert_any_call("device_telemetry", {
            "id": "!ina_node_03",
            "battery": 100,
            "voltage": 4.30,
            "channel_util": None,
            "air_util_tx": None,
            "uptime_seconds": None,
            "power_ina1": 3.71,
            "power_ina2": 4.18,
            "power_ina3": 3.52,
        })

    def test_request_telemetry_power_metrics(self):
        interface = SerialInterface(serial_port="/dev/null")
        interface.interface = MagicMock()
        mock_send_data = MagicMock()
        interface.interface.sendData = mock_send_data

        ok = interface.request_telemetry("!12345678", channel_index=0, telemetry_type="power_metrics")
        self.assertTrue(ok)
        mock_send_data.assert_called_once()
        kargs = mock_send_data.call_args[1]
        self.assertEqual(kargs.get("destinationId"), "!12345678")
        self.assertEqual(kargs.get("wantResponse"), True)
        sent_payload = mock_send_data.call_args[0][0]
        self.assertTrue(sent_payload.HasField("power_metrics"))
        self.assertFalse(sent_payload.HasField("device_metrics"))

    def test_request_telemetry_device_metrics(self):
        interface = SerialInterface(serial_port="/dev/null")
        interface.interface = MagicMock()
        mock_send_data = MagicMock()
        interface.interface.sendData = mock_send_data

        ok = interface.request_telemetry("!12345678", channel_index=0, telemetry_type="device_metrics")
        self.assertTrue(ok)
        mock_send_data.assert_called_once()
        kargs = mock_send_data.call_args[1]
        self.assertEqual(kargs.get("destinationId"), "!12345678")
        self.assertEqual(kargs.get("wantResponse"), True)
        sent_payload = mock_send_data.call_args[0][0]
        self.assertTrue(sent_payload.HasField("device_metrics"))
        self.assertFalse(sent_payload.HasField("power_metrics"))

    def test_gateway_enqueues_power_telemetry(self):
        import asyncio
        from Services.Gateway import GatewayService
        gateway = GatewayService()
        gateway.db = self.db
        
        # Test default / device_metrics
        resp_bat = asyncio.run(gateway._handle_action(None, {"action": "request_telemetry", "params": {"node_id": "!node_bat"}}))
        self.assertTrue(resp_bat.get("success"))
        msg_bat = self.db.get_next_pending_outbox()
        self.assertIsNotNone(msg_bat)
        self.assertEqual(msg_bat["text"], "__REQ_TELEMETRY__")
        self.assertEqual(msg_bat["dest"], "!node_bat")
        self.db.mark_outbox_sent(msg_bat["id"])

        # Test power_metrics via telemetry_type
        resp_pwr = asyncio.run(gateway._handle_action(None, {"action": "request_telemetry", "params": {"node_id": "!node_pwr", "telemetry_type": "power_metrics"}}))
        self.assertTrue(resp_pwr.get("success"))
        msg_pwr = self.db.get_next_pending_outbox()
        self.assertIsNotNone(msg_pwr)
        self.assertEqual(msg_pwr["text"], "__REQ_POWER_TELEMETRY__")
        self.assertEqual(msg_pwr["dest"], "!node_pwr")
        self.db.mark_outbox_sent(msg_pwr["id"])


if __name__ == "__main__":
    unittest.main()

