from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from Models.Database import Database
from Models.Node import Node
from create_db import ensure_database
import cron_tasks


class TestTracesSchedule(unittest.TestCase):

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".sql", delete=False)
        self.tmp_db.close()
        ensure_database(self.tmp_db.name)
        self.db = Database(self.tmp_db.name)

    def tearDown(self):
        if os.path.exists(self.tmp_db.name):
            os.remove(self.tmp_db.name)

    def _create_node(self, node_id: str, short_name: str, role: int = 0, hops: int = 1, last_heard: int = None, updated_at: str = None):
        with self.db._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO nodes (node_id, num, short_name, name, role, hops, last_heard, via_mqtt, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, datetime('now','localtime'), ?)""",
                (
                    node_id, 123, short_name, f"Node {short_name}", role, hops,
                    last_heard or int(datetime.now().timestamp()),
                    updated_at or datetime.now().isoformat()
                )
            )
            conn.commit()

    def test_client_reload_5_days_and_5_consecutive_errors(self):
        """Verifica que los clientes respetan 5 días (120h) y se descartan tras 5 fallos consecutivos."""
        now = datetime.now()
        node_id = "!node_cli_1"
        initial_time = now - timedelta(days=2)
        self._create_node(
            node_id, "CLI1", role=0, hops=1,
            last_heard=int(initial_time.timestamp()),
            updated_at=initial_time.isoformat()
        )

        # 1. Sin trazas previas -> es candidato
        cand = self.db.get_next_node_to_trace(reload_hours=120, retry_hours=24)
        self.assertEqual(cand, node_id)

        # 2. Con traza exitosa hace 3 días (72h < 120h) -> NO es candidato
        t_id = self.db.enqueue_trace(node_id)
        self.db.mark_trace_done_with_route(t_id, True, text="ok")
        three_days_ago = (now - timedelta(days=3)).isoformat()
        with self.db._connect() as conn:
            conn.execute("UPDATE traces SET updated_at = ? WHERE id = ?", (three_days_ago, t_id))
            conn.commit()

        cand = self.db.get_next_node_to_trace(reload_hours=120, retry_hours=24)
        self.assertIsNone(cand)

        # 3. Con traza exitosa hace 6 días (144h >= 120h) -> VUELVE a ser candidato
        six_days_ago = (now - timedelta(days=6)).isoformat()
        with self.db._connect() as conn:
            conn.execute("UPDATE traces SET updated_at = ? WHERE id = ?", (six_days_ago, t_id))
            conn.commit()

        cand = self.db.get_next_node_to_trace(reload_hours=120, retry_hours=24)
        self.assertEqual(cand, node_id)

        # 4. Insertar 5 fallos consecutivos posteriores (hace entre 30 y 26 horas)
        # Dejando el nodo con last_heard antiguo de hace 2 días (hace 48 horas)
        old_activity = now - timedelta(hours=48)
        with self.db._connect() as conn:
            conn.execute("UPDATE nodes SET last_heard = ?, updated_at = ? WHERE node_id = ?",
                         (int(old_activity.timestamp()), old_activity.isoformat(), node_id))
            conn.commit()

        for i in range(5):
            t_err = self.db.enqueue_trace(node_id)
            self.db.mark_trace_done_with_route(t_err, False, text="err")
            err_date = (now - timedelta(hours=30 - i)).isoformat()
            with self.db._connect() as conn:
                conn.execute("UPDATE traces SET updated_at = ? WHERE id = ?", (err_date, t_err))
                conn.commit()

        # El último fallo fue hace 26h (>=24h), pero tiene 5 errores consecutivos posteriores a su última actividad -> descartado
        cand = self.db.get_next_node_to_trace(reload_hours=120, retry_hours=24)
        self.assertIsNone(cand)

        # 5. El nodo emite un paquete nuevo (last_heard posterior al último error) -> reactivado
        new_last_heard = int((now + timedelta(seconds=10)).timestamp())
        with self.db._connect() as conn:
            conn.execute("UPDATE nodes SET last_heard = ?, updated_at = ? WHERE node_id = ?",
                         (new_last_heard, (now + timedelta(seconds=10)).isoformat(), node_id))
            conn.commit()

        cand = self.db.get_next_node_to_trace(reload_hours=120, retry_hours=24)
        self.assertEqual(cand, node_id)

    def test_router_prioritized_at_06_am(self):
        """Verifica que a las 06:00 AM un router prioritario tiene precedencia."""
        now = datetime.now()
        r_id = "!router_1"
        c_id = "!client_1"

        self._create_node(r_id, "CA12", role=2, hops=1, last_heard=int(now.timestamp()))
        self._create_node(c_id, "CLI2", role=0, hops=1, last_heard=int(now.timestamp()))

        with patch("Models.Database.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 8, 31, 6, 15, 0)
            mock_dt.fromisoformat = datetime.fromisoformat
            cand = self.db.get_next_node_to_trace(router_start_hour=6, router_identifiers=["CA12"])
            self.assertEqual(cand, r_id)

    def test_send_trace_throttling_diurno_vs_nocturno_vs_router(self):
        """Verifica que send_trace aplica 40s a routers, 60m diurno y 5m nocturno."""
        r_id1 = "!router_1"
        r_id2 = "!router_2"
        now = datetime.now()

        # Creamos 2 routers que necesitan trace matinal
        self._create_node(r_id1, "CA12", role=2, hops=1, last_heard=int(now.timestamp()))
        self._create_node(r_id2, "CA13", role=2, hops=1, last_heard=int(now.timestamp()))

        # Router 1 terminado hace 30 segundos (< 40s)
        t_id = self.db.enqueue_trace(r_id1)
        self.db.mark_trace_done_with_route(t_id, True, text="ok")
        thirty_sec_ago = (now - timedelta(seconds=30)).isoformat()
        with self.db._connect() as conn:
            conn.execute("UPDATE traces SET updated_at = ? WHERE id = ?", (thirty_sec_ago, t_id))
            conn.commit()

        with patch("cron_tasks.env") as mock_env, patch("cron_tasks.Database", return_value=self.db):
            mock_env.ENABLE_TRACES = True
            mock_env.ROUTER_TRACE_INTERVAL_SECONDS = 40
            mock_env.ROUTER_NODES = ["CA12", "CA13"]
            mock_env.ROUTER_TRACE_START_HOUR = 6
            mock_env.TRACES_INTERVAL_PEAK = 60
            mock_env.TRACES_INTERVAL_OFFPEAK = 5
            mock_env.TRACES_PEAK_START_HOUR = 8
            mock_env.TRACES_PEAK_END_HOUR = 23

            # Mockeamos a las 06:15 AM
            with patch("cron_tasks.datetime") as mock_dt:
                mock_dt.now.return_value = now
                mock_dt.fromisoformat = datetime.fromisoformat

                # 30s después -> no debe encolar porque faltan 10s para el throttle de 40s
                cron_tasks.send_trace()
                self.assertIsNone(self.db.get_next_pending_trace())

                # 50s después -> debe encolar el router 2
                fifty_sec_ago = (now - timedelta(seconds=50)).isoformat()
                with self.db._connect() as conn:
                    conn.execute("UPDATE traces SET updated_at = ? WHERE id = ?", (fifty_sec_ago, t_id))
                    conn.commit()

                cron_tasks.send_trace()
                pending = self.db.get_next_pending_trace()
                self.assertIsNotNone(pending)
                self.assertEqual(pending['to'], r_id2)


if __name__ == "__main__":
    unittest.main()
