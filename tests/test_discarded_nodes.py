from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from Models.Database import Database
from Models.MeshWatcher import MeshWatcher
from Models.Node import Node
from Models.SerialInterface import SerialInterface
from create_db import ensure_database
from functions import (
    get_discarded_nodes_config,
    is_node_discarded,
    register_discarded_node_id,
    reset_discarded_nodes_cache,
)


class TestDiscardedNodes(unittest.TestCase):

    def setUp(self):
        reset_discarded_nodes_cache()
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_discarded.sql")
        ensure_database(self.db_path)
        self.db = Database(self.db_path)

        # Redirigir Database() al archivo temporal
        self.orig_init = Database.__init__
        test_path = self.db_path
        Database.__init__ = lambda self, path=test_path: self.orig_init(path or test_path) if hasattr(self, 'orig_init') else setattr(self, 'db_path', path or test_path)

        # Resetear MeshWatcher
        MeshWatcher._last_telemetry = {}
        MeshWatcher._ignored_nodes = set()
        MeshWatcher._initialized = False

    def tearDown(self):
        Database.__init__ = self.orig_init
        reset_discarded_nodes_cache()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("env.DISCARDED_NODES", ["Ben4"])
    def test_is_node_discarded_by_short_name(self):
        self.assertTrue(is_node_discarded(short_name="Ben4"))
        self.assertTrue(is_node_discarded(short_name="ben4"))
        self.assertTrue(is_node_discarded(short_name="BEN4"))
        self.assertFalse(is_node_discarded(short_name="RAU0"))
        self.assertFalse(is_node_discarded(short_name=None))

    @patch("env.DISCARDED_NODES", ["Ben4"])
    def test_dynamic_id_memorization(self):
        # 1. Al comprobar con short_name e id nuevo, se memoriza el id
        node_id = "!random123"
        self.assertTrue(is_node_discarded(node_id=node_id, short_name="Ben4"))

        # 2. Ahora, comprobando SOLO con node_id, debe reconocerse inmediatamente
        self.assertTrue(is_node_discarded(node_id=node_id))
        self.assertTrue(is_node_discarded(node_id="!random123"))

    @patch("env.DISCARDED_NODES", ["Ben4"])
    def test_database_refuses_to_create_or_update_discarded_node(self):
        node_id = "!ben4test"

        # Intentar crear nodo con short_name Ben4
        self.db.create_node_if_not_exists(node_id, {"short_name": "Ben4", "name": "Benthur4"})
        row = self.db.get_node(node_id)
        self.assertIsNone(row)

        # Intentar update_node
        self.db.update_node(node_id, {"short_name": "Ben4"})
        row = self.db.get_node(node_id)
        self.assertIsNone(row)

    @patch("env.DISCARDED_NODES", ["Ben4"])
    def test_database_purges_existing_node_on_update(self):
        node_id = "!existingnode"

        # Insertar nodo directamente simulando que existía antes de saber su nombre
        with self.db._connect() as conn:
            conn.execute(
                "INSERT INTO nodes (node_id, created_at, updated_at) VALUES (?, '2026-09-22', '2026-09-22')",
                (node_id,)
            )
            conn.commit()

        self.assertIsNotNone(self.db.get_node(node_id))

        # Al actualizar con short_name Ben4, debe ser purgado de nodes
        self.db.update_node(node_id, {"short_name": "Ben4", "name": "Benthur4"})
        self.assertIsNone(self.db.get_node(node_id))

    @patch("env.DISCARDED_NODES", ["Ben4"])
    def test_save_ping_refuses_discarded_node(self):
        ret = self.db.save_ping(
            from_id="!ben4ping",
            to_id="^all",
            from_name="Ben4",
            hops=1,
            data_raw="{}"
        )
        self.assertEqual(ret, 0)

        # Comprobar que no se insertó en pings
        with self.db._connect() as conn:
            cnt = conn.execute("SELECT count(*) FROM pings WHERE from_name = 'Ben4'").fetchone()[0]
            self.assertEqual(cnt, 0)

    @patch("env.DISCARDED_NODES", ["Ben4"])
    def test_mesh_watcher_discards_packet(self):
        packet = {
            "fromId": "!ben4watcher",
            "from": 999999,
            "hopStart": 7,  # Normalmente causaría auto-reporte
            "decoded": {
                "portnum": "TEXT_MESSAGE_APP",
                "text": "Tráfico de test",
            },
        }
        node_info = MagicMock()
        node_info.short_name = "Ben4"
        node_info.name = "Benthur4"

        discard = MeshWatcher.inspect_packet(packet, from_node_info=node_info)
        self.assertTrue(discard)

        # Verificar que no se registró ningún auto_reported_node
        reported = self.db.get_auto_reported_nodes()
        self.assertEqual(len(reported), 0)

    @patch("env.DISCARDED_NODES", ["Ben4"])
    def test_serial_interface_handlers_drop_discarded_nodes(self):
        si = SerialInterface("/dev/null")
        si.node_dict = {}

        # 1. on_receive_user
        user_packet = {
            "from": 123456,
            "decoded": {
                "user": {
                    "id": "!ben4user",
                    "shortName": "Ben4",
                    "longName": "Benthur4",
                }
            }
        }
        si.on_receive_user(user_packet, interface=None)
        self.assertNotIn("!ben4user", si.node_dict)
        self.assertIsNone(self.db.get_node("!ben4user"))

        # 2. on_receive_data con el mismo id (debe estar en caché dinámica)
        data_packet = {
            "fromId": "!ben4user",
            "from": 123456,
            "decoded": {
                "telemetry": {
                    "deviceMetrics": {"batteryLevel": 95, "voltage": 4.1}
                }
            }
        }
        si.on_receive_data(data_packet, interface=None)
        self.assertIsNone(self.db.get_node("!ben4user"))

        # 3. on_receive_text con el mismo id
        text_packet = {
            "fromId": "!ben4user",
            "from": 123456,
            "decoded": {
                "text": "/ping"
            }
        }
        si.on_receive_text(text_packet, interface=None)
        self.assertIsNone(self.db.get_node("!ben4user"))

    @patch("env.DISCARDED_NODES", ["Ben4"])
    def test_schema_purge_cleans_existing_records(self):
        # Insertar nodos y pings de Ben4
        with self.db._connect() as conn:
            conn.execute("INSERT INTO nodes (node_id, short_name, name) VALUES ('!old1', 'Ben4', 'Benthur4')")
            conn.execute("INSERT INTO nodes (node_id, short_name, name) VALUES ('!old2', 'RAU0', 'Router RAU0')")
            conn.execute("INSERT INTO pings (\"from\", \"to\", from_name, data_raw) VALUES ('!old1', '^all', 'Ben4', '{}')")
            conn.commit()

        # Re-ejecutar ensure_database para simular arranque/migración
        ensure_database(self.db_path)

        with self.db._connect() as conn:
            ben_nodes = conn.execute("SELECT count(*) FROM nodes WHERE short_name = 'Ben4'").fetchone()[0]
            self.assertEqual(ben_nodes, 0)

            rau_nodes = conn.execute("SELECT count(*) FROM nodes WHERE short_name = 'RAU0'").fetchone()[0]
            self.assertEqual(rau_nodes, 1)

            ben_pings = conn.execute("SELECT count(*) FROM pings WHERE from_name = 'Ben4'").fetchone()[0]
            self.assertEqual(ben_pings, 0)


if __name__ == "__main__":
    unittest.main()
