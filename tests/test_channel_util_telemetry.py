from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from Models.Database import Database
from Models.Node import Node
from create_db import ensure_database


class TestChannelUtilTelemetry(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_telem.sql"
        ensure_database(self.db_path)
        self.db = Database(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_update_and_get_node_channel_util(self):
        node_id = "!aabb1122"
        self.db.create_node_if_not_exists(node_id)
        
        # Actualizar telemetría de saturación y tiempo de emisión
        self.db.update_node(node_id, {
            "name": "Nodo Carga",
            "channel_util": 14.5,
            "air_util_tx": 1.25,
        })
        
        # Recuperar nodo individualmente
        node_row = self.db.get_node(node_id)
        self.assertIsNotNone(node_row)
        self.assertEqual(node_row.get("channel_util"), 14.5)
        self.assertEqual(node_row.get("air_util_tx"), 1.25)
        
        # Recuperar nodo por get_all_nodes
        all_nodes = self.db.get_all_nodes()
        found = next((n for n in all_nodes if n.get("node_id") == node_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found.get("channel_util"), 14.5)
        self.assertEqual(found.get("air_util_tx"), 1.25)

    def test_node_model_extracts_channel_util_from_device_metrics(self):
        node_id = "!aabb3344"
        with patch('Models.Node.Database', return_value=self.db):
            node = Node(node_id)
            self.assertIsNone(node.channel_util)
            self.assertIsNone(node.air_util_tx)
            
            # Simular paquete con deviceMetrics
            node.update_metadata({
                "name": "Router Test",
                "short_name": "ROUT",
                "deviceMetrics": {
                    "batteryLevel": 88,
                    "voltage": 4.12,
                    "channelUtilization": 28.736,
                    "airUtilTx": 0.452,
                }
            })
            
            # Redondeo a 2 decimales
            self.assertEqual(node.channel_util, 28.74)
            self.assertEqual(node.air_util_tx, 0.45)
            
            metadata = node.get_metadata()
            self.assertEqual(metadata.get("channel_util"), 28.74)
            self.assertEqual(metadata.get("air_util_tx"), 0.45)
            
            # Comprobar persistencia en base de datos
            db_row = self.db.get_node(node_id)
            self.assertEqual(db_row.get("channel_util"), 28.74)
            self.assertEqual(db_row.get("air_util_tx"), 0.45)

    def test_serial_interface_on_receive_data_persists_channel_metrics(self):
        from Models.SerialInterface import SerialInterface
        
        node_id = "!aabb5566"
        self.db.create_node_if_not_exists(node_id)
        
        serial_inst = SerialInterface.__new__(SerialInterface)
        serial_inst.node_dict = {}
        serial_inst.interface = MagicMock()
        serial_inst.serial_port = "/dev/null"
        serial_inst._touch_rx = MagicMock()
        
        packet = {
            "fromId": node_id,
            "toId": "^all",
            "rxSnr": 9.5,
            "rxRssi": -65,
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {
                    "deviceMetrics": {
                        "batteryLevel": 95,
                        "voltage": 4.18,
                        "channelUtilization": 8.35,
                        "airUtilTx": 0.12,
                    }
                }
            }
        }
        
        with patch('Models.Database.Database', return_value=self.db), \
             patch('Models.EventBroadcaster.broadcast_event'):
            serial_inst.on_receive_data(packet, serial_inst.interface)
            
            db_row = self.db.get_node(node_id)
            self.assertIsNotNone(db_row)
            self.assertEqual(db_row.get("channel_util"), 8.35)
            self.assertEqual(db_row.get("air_util_tx"), 0.12)


if __name__ == "__main__":
    unittest.main()
