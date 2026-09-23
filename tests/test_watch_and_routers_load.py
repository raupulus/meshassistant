import unittest
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from create_db import ensure_database
from Models.Database import Database
from Models.Node import Node
from Services.Gateway import GatewayService


class TestWatchAndRoutersLoad(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_watch.sql"
        ensure_database(self.db_path)
        self.db = Database(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_watch_and_telemetry_count(self):
        node_id = "!node1234"
        self.db.create_node_if_not_exists(node_id)

        # Por defecto is_watched=0, telemetry_count=0
        node = self.db.get_node(node_id)
        self.assertEqual(node.get("is_watched"), 0)
        self.assertEqual(node.get("telemetry_count"), 0)

        # Marcar vigilado
        self.db.set_node_watched(node_id, True)
        self.assertEqual(self.db.get_node(node_id).get("is_watched"), 1)

        # Desmarcar vigilado
        self.db.set_node_watched(node_id, False)
        self.assertEqual(self.db.get_node(node_id).get("is_watched"), 0)

        # Incrementar conteo de telemetría
        self.db.increment_node_telemetry_count(node_id)
        self.db.increment_node_telemetry_count(node_id)
        self.assertEqual(self.db.get_node(node_id).get("telemetry_count"), 2)

    def test_node_model_watch_and_telemetry(self):
        node_id = "!node5678"
        self.db.create_node_if_not_exists(node_id)
        self.db.update_node(node_id, {
            "name": "Router Test",
            "is_watched": True,
            "telemetry_count": 5,
            "traces_detected": 3,
        })

        with patch("Models.Node.Database", return_value=self.db):
            node = Node(node_id)
            self.assertTrue(node.is_watched)
            self.assertEqual(node.telemetry_count, 5)
            self.assertEqual(node.traces_detected, 3)

            meta = node.get_metadata()
            self.assertTrue(meta["is_watched"])
            self.assertEqual(meta["telemetry_count"], 5)
            self.assertEqual(meta["traces_detected"], 3)

            # Actualización normal sin borrar is_watched
            node.update_metadata({"snr": 10.5})
            self.assertTrue(node.is_watched)
            self.assertEqual(self.db.get_node(node_id).get("is_watched"), 1)

    def test_auto_report_join_in_get_all_nodes_and_routers(self):
        node_id = "!badactor01"
        self.db.create_node_if_not_exists(node_id)
        self.db.update_node(node_id, {"name": "Bad Node"})

        # Insertar aviso de seguridad en auto_reported_nodes
        conn = self.db._connect()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO auto_reported_nodes (node_id, reason_code, reason_desc, event_count, first_detected_at, last_detected_at, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'))",
            (node_id, "FLOOD_TELEMETRY", "Envío excesivo de telemetría", 3)
        )
        conn.commit()
        conn.close()

        nodes = self.db.get_all_nodes()
        found = next((n for n in nodes if n["id"] == node_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found.get("auto_report_count"), 3)
        self.assertIn("FLOOD_TELEMETRY", found.get("auto_report_reason"))

    def test_gateway_set_node_watched_action(self):
        gw = GatewayService()
        gw.db = self.db
        node_id = "!node9999"
        self.db.create_node_if_not_exists(node_id)

        # Probar la acción set_node_watched mediante process_action
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            res = loop.run_until_complete(
                gw._handle_action(None, {"action": "set_node_watched", "params": {"node_id": node_id, "is_watched": True}})
            )
            self.assertTrue(res["success"])
            self.assertEqual(res["data"]["is_watched"], True)
            self.assertEqual(self.db.get_node(node_id).get("is_watched"), 1)

            res2 = loop.run_until_complete(
                gw._handle_action(None, {"action": "set_node_watched", "params": {"node_id": node_id, "is_watched": False}})
            )
            self.assertTrue(res2["success"])
            self.assertEqual(res2["data"]["is_watched"], False)
            self.assertEqual(self.db.get_node(node_id).get("is_watched"), 0)
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
