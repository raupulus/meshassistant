from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest

from Models.Database import Database
from Models.MeshWatcher import MeshWatcher
from Models.Node import Node
from create_db import ensure_database


class TestLastHeardSync(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_last_heard.sql")
        ensure_database(self.db_path)
        self.db = Database(self.db_path)

        # Redirigir Database() al archivo temporal
        orig_init = Database.__init__
        self.orig_init = orig_init
        test_path = self.db_path
        Database.__init__ = lambda db_inst, path=test_path: orig_init(db_inst, path or test_path)

        # Resetear estado estático de MeshWatcher
        MeshWatcher._last_telemetry = {}
        MeshWatcher._ignored_nodes = set()
        MeshWatcher._local_node_ids = set()
        MeshWatcher._local_node_names = set()
        MeshWatcher._initialized = False

    def tearDown(self):
        Database.__init__ = self.orig_init
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_touch_node_last_heard(self):
        node_id = "!test0001"
        t1 = 1758600000
        self.db.touch_node_last_heard(node_id, last_heard=t1, short_name="tst1", name="Test Node 1")

        n = self.db.get_node(node_id)
        self.assertIsNotNone(n)
        self.assertEqual(n["last_heard"], t1)
        self.assertEqual(n["short_name"], "tst1")
        self.assertEqual(n["name"], "Test Node 1")

        # Probar que last_heard nunca retrocede si llega un timestamp menor
        t0 = 1758500000
        self.db.touch_node_last_heard(node_id, last_heard=t0)
        n = self.db.get_node(node_id)
        self.assertEqual(n["last_heard"], t1)

        # Probar avance con timestamp más nuevo
        t2 = 1758650000
        self.db.touch_node_last_heard(node_id, last_heard=t2)
        n = self.db.get_node(node_id)
        self.assertEqual(n["last_heard"], t2)

    def test_node_model_updates_last_heard(self):
        node_id = "!test0002"
        n = Node(node_id)
        t1 = 1758610000
        n.update_metadata({"name": "Node 2", "lastHeard": t1})
        self.assertEqual(n.last_heard, t1)

        # Persistido en BD
        db_n = self.db.get_node(node_id)
        self.assertIsNotNone(db_n)
        self.assertEqual(db_n["last_heard"], t1)

    def test_mesh_watcher_touches_last_heard(self):
        node_id = "!test0003"
        t_rx = 1758620000
        packet = {
            "fromId": node_id,
            "from": 12345,
            "hopStart": 3,
            "hopLimit": 2,
            "rxTime": t_rx,
            "rxSnr": 9.5,
            "rxRssi": -65,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "ping"},
        }
        MeshWatcher.inspect_packet(packet)

        db_n = self.db.get_node(node_id)
        self.assertIsNotNone(db_n)
        self.assertEqual(db_n["last_heard"], t_rx)
        self.assertEqual(db_n["snr"], 9.5)

    def test_migration_syncs_from_auto_reported_nodes(self):
        node_id = "!150dbd0f"
        # Simular situación descrita por el usuario: nodo existente con last_heard NULL y detección en seguridad
        self.db.create_node_if_not_exists(node_id, {
            "short_name": "vent",
            "name": "Venturada2 🌞🗼",
        })
        with self.db._connect() as conn:
            conn.execute("UPDATE nodes SET last_heard = NULL, updated_at = '2026-09-23T00:30:14' WHERE node_id = ?", (node_id,))
            conn.execute(
                """
                INSERT INTO auto_reported_nodes (
                    node_id, short_name, name, reason_code, reason_desc,
                    event_count, first_detected_at, last_detected_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, '2026-09-23T08:31:30', '2026-09-23T08:31:30', '2026-09-23T08:31:30')
                """,
                (node_id, "vent", "Venturada2 🌞🗼", "EXCESSIVE_HOPS", "Configurado con 6 saltos"),
            )
            conn.commit()

        # Ejecutar ensure_database (migración)
        ensure_database(self.db_path)

        n = self.db.get_node(node_id)
        self.assertIsNotNone(n)
        self.assertIsNotNone(n["last_heard"])
        # La migración convierte la hora local naive (Madrid CEST UTC+2) a UTC estricto con sufijo Z
        self.assertEqual(n["updated_at"], "2026-09-23T06:31:30Z")


if __name__ == "__main__":
    unittest.main()
