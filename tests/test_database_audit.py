import unittest
import os
import tempfile
import shutil
from Models.Database import Database
from create_db import ensure_database


class TestDatabaseAudit(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_audit.sql")
        ensure_database(self.db_path)
        self.db = Database(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_commands_audit_and_ranking(self):
        # Insertar nodos
        self.db.create_node_if_not_exists("!11111111")
        self.db.update_node("!11111111", {"name": "Nodo Uno", "short_name": "N1", "role": 1})
        self.db.create_node_if_not_exists("!22222222")
        self.db.update_node("!22222222", {"name": "Nodo Dos", "short_name": "N2", "role": 2})

        # Insertar comandos
        self.db.log_command(node_id="!11111111", command="ping", message="test ping", parameters="")
        self.db.log_command(node_id="!11111111", command="weather", message="test weather", parameters="Cadiz")
        self.db.log_command(node_id="!22222222", command="ping", message="test ping 2", parameters="")

        # 1. get_commands_audit
        audit_logs = self.db.get_commands_audit(limit=10)
        self.assertEqual(len(audit_logs), 3)
        self.assertEqual(audit_logs[0]["name"], "Nodo Dos")
        self.assertEqual(audit_logs[0]["command"], "ping")

        # 2. get_top_command_users
        ranking = self.db.get_top_command_users(limit=5, hours=24)
        self.assertEqual(len(ranking), 2)
        # El nodo 1 tiene 2 comandos
        self.assertEqual(ranking[0]["node_id"], "!11111111")
        self.assertEqual(ranking[0]["count"], 2)
        self.assertEqual(ranking[0]["short_name"], "N1")

        # 3. get_commands_audit_summary
        summary = self.db.get_commands_audit_summary(hours=24)
        self.assertEqual(summary["total_24h"], 3)
        self.assertEqual(summary["unique_nodes_24h"], 2)
        self.assertEqual(summary["top_command_24h"], "ping")
        self.assertEqual(summary["top_command_count"], 2)


if __name__ == "__main__":
    unittest.main()
