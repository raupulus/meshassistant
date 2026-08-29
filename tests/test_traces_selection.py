from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import create_db
import env
from Models.Database import Database
from Models.SerialInterface import SerialInterface
import cron_tasks


class TestTracesSelection(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_traces.sql")
        create_db.ensure_database(self.db_path)
        self.db = Database(self.db_path)

        # Redirigir Database() por defecto al archivo temporal
        self.orig_init = Database.__init__
        test_path = self.db_path
        Database.__init__ = lambda self, path=test_path: self.orig_init(path or test_path) if hasattr(self, 'orig_init') else setattr(self, 'db_path', path or test_path)

    def tearDown(self):
        Database.__init__ = self.orig_init
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_hops_base_compensation(self):
        """Comprueba que hops_limit=2 acepta nodos hasta hops=3 (2 exteriores + 1 base)."""
        now_epoch = int(time.time())
        # Nodo a 3 saltos brutos (2 exteriores + 1 local)
        self.db.create_node_if_not_exists("!node3hops")
        self.db.update_node("!node3hops", {
            "name": "Nodo a 3 saltos",
            "hops": 3,
            "last_heard": now_epoch,
        })

        # Nodo a 4 saltos brutos (3 exteriores + 1 local) -> debe ser excluido
        self.db.create_node_if_not_exists("!node4hops")
        self.db.update_node("!node4hops", {
            "name": "Nodo a 4 saltos",
            "hops": 4,
            "last_heard": now_epoch,
        })

        candidate = self.db.get_next_node_to_trace(hops_limit=2)
        self.assertEqual(candidate, "!node3hops")

    def test_inactive_7_days_discard(self):
        """Comprueba que nodos con last_heard de más de 7 días no se trazan."""
        old_epoch = int(time.time()) - (8 * 86400)  # Hace 8 días
        recent_epoch = int(time.time()) - (2 * 86400) # Hace 2 días

        # Nodo inactivo hace 8 días
        self.db.create_node_if_not_exists("!old_tourist")
        self.db.update_node("!old_tourist", {
            "name": "Turista antiguo",
            "hops": 2,
            "last_heard": old_epoch,
        })

        # No debe haber candidato
        candidate = self.db.get_next_node_to_trace(hops_limit=2, max_inactive_days=7)
        self.assertIsNone(candidate)

        # Si el nodo emite señal reciente (hace 2 días), vuelve a ser candidato
        self.db.update_node("!old_tourist", {
            "last_heard": recent_epoch,
        })
        candidate2 = self.db.get_next_node_to_trace(hops_limit=2, max_inactive_days=7)
        self.assertEqual(candidate2, "!old_tourist")

    def test_router_routine_after_5_am(self):
        """Comprueba que la rutina de routers se permite después de las 05:00 AM y se pausa antes."""
        now_epoch = int(time.time())
        self.db.create_node_if_not_exists("!router1")
        self.db.update_node("!router1", {
            "name": "Router Test",
            "role": 2,  # ROUTER
            "hops": 2,
            "last_heard": now_epoch,
        })

        # Simular hora 04:00 AM (antes de las 05:00) -> No debe devolver router rutinario
        with patch("Models.Database.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 8, 29, 4, 30, 0)
            mock_dt.fromisoformat = datetime.fromisoformat
            candidate_early = self.db.get_next_node_to_trace(router_start_hour=5)
            self.assertIsNone(candidate_early)

        # Simular hora 05:30 AM -> Sí debe devolver el router
        with patch("Models.Database.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 8, 29, 5, 30, 0)
            mock_dt.fromisoformat = datetime.fromisoformat
            candidate_morning = self.db.get_next_node_to_trace(router_start_hour=5)
            self.assertEqual(candidate_morning, "!router1")

    def test_request_router_telemetry_cron(self):
        """Comprueba que request_router_telemetry encola __REQ_TELEMETRY__ a las 07:00 AM."""
        self.db.create_node_if_not_exists("!router_batt")
        self.db.update_node("!router_batt", {
            "name": "Router Batería",
            "short_name": "RBAT",
            "role": 2,
            "hops": 2,
        })
        self.db.save_trace("local", "!router_batt", "ok")
        env.ROUTER_NODES = ['!router_batt']

        with patch("cron_tasks.datetime") as mock_dt:
            # Antes de las 07:00 AM -> no encola
            mock_dt.now.return_value = datetime(2026, 8, 29, 6, 45, 0)
            mock_dt.fromisoformat = datetime.fromisoformat
            cron_tasks.request_router_telemetry()
            self.assertIsNone(self.db.get_next_pending_outbox())

            # A las 07:15 AM -> encola petición de telemetría
            mock_dt.now.return_value = datetime(2026, 8, 29, 7, 15, 0)
            cron_tasks.request_router_telemetry()
            pending = self.db.get_next_pending_outbox()
            self.assertIsNotNone(pending)
            self.assertEqual(pending["text"], "__REQ_TELEMETRY__")
            self.assertEqual(pending["dest"], "!router_batt")


if __name__ == "__main__":
    unittest.main()
