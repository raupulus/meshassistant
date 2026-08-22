import unittest
import os
import tempfile
import shutil
from Models.Database import Database
from create_db import ensure_database
from data import commands_dict


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

        # 1. get_commands_audit con limit y offset
        audit_logs = self.db.get_commands_audit(limit=2, offset=0)
        self.assertEqual(len(audit_logs), 2)
        self.assertEqual(audit_logs[0]["name"], "Nodo Dos")
        self.assertEqual(audit_logs[0]["command"], "ping")

        audit_page2 = self.db.get_commands_audit(limit=2, offset=2)
        self.assertEqual(len(audit_page2), 1)
        self.assertEqual(audit_page2[0]["command"], "ping")

        # 2. get_top_command_users
        ranking = self.db.get_top_command_users(limit=20, hours=24)
        self.assertEqual(len(ranking), 2)
        self.assertEqual(ranking[0]["node_id"], "!11111111")
        self.assertEqual(ranking[0]["count"], 2)
        self.assertEqual(ranking[0]["short_name"], "N1")

        # 3. get_commands_audit_summary
        summary = self.db.get_commands_audit_summary(hours=24)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["unique_nodes"], 2)
        self.assertEqual(summary["top_command"], "ping")
        self.assertEqual(summary["top_command_count"], 2)

    def test_nodes_created_at_and_nodeinfo_outbox(self):
        self.db.create_node_if_not_exists("!33333333")
        nodes = self.db.get_all_nodes()
        self.assertTrue(len(nodes) >= 1)
        target = [n for n in nodes if n["node_id"] == "!33333333"][0]
        self.assertIn("created_at", target)
        self.assertTrue(bool(target["created_at"]))

        # Encolar petición de NodeInfo
        out_id = self.db.enqueue_outbox("__REQ_NODEINFO__", dest="!33333333", channel=0)
        pending = self.db.get_next_pending_outbox()
        self.assertIsNotNone(pending)
        self.assertEqual(pending["id"], out_id)
        self.assertEqual(pending["text"], "__REQ_NODEINFO__")
        self.assertEqual(pending["dest"], "!33333333")

    def test_test_command_registered(self):
        self.assertIn("test", commands_dict)
        self.assertEqual(commands_dict["test"]["callback"], commands_dict["ping"]["callback"])


if __name__ == "__main__":
    unittest.main()
