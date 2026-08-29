from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from Models.Database import Database
from Models.MeshWatcher import MeshWatcher
from create_db import ensure_database


class TestMeshWatcher(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_watcher.sql")
        ensure_database(self.db_path)
        self.db = Database(self.db_path)

        # Redirigir Database() por defecto al archivo temporal del test
        self.orig_init = Database.__init__
        test_path = self.db_path
        Database.__init__ = lambda self, path=test_path: self.orig_init(path or test_path) if hasattr(self, 'orig_init') else setattr(self, 'db_path', path or test_path)

        # Resetear estado estático del MeshWatcher
        MeshWatcher._last_telemetry = {}
        MeshWatcher._ignored_nodes = set()
        MeshWatcher._local_node_ids = set()
        MeshWatcher._local_node_names = set()
        MeshWatcher._initialized = False

    def tearDown(self):
        Database.__init__ = self.orig_init
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_excessive_hops_detection(self):
        packet = {
            "fromId": "!badhop1",
            "from": 1234567,
            "hopStart": 7,
            "hopLimit": 4,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "Hola mundo"},
        }
        discard = MeshWatcher.inspect_packet(packet)
        self.assertFalse(discard)

        reported = self.db.get_auto_reported_nodes()
        self.assertEqual(len(reported), 1)
        self.assertEqual(reported[0]["node_id"], "!badhop1")
        self.assertEqual(reported[0]["reason_code"], "EXCESSIVE_HOPS")
        self.assertEqual(reported[0]["reason_desc"], "Configurado con 7 saltos iniciales")
        self.assertEqual(reported[0]["event_count"], 1)

        # Repetir el mismo paquete para comprobar incremento de event_count
        MeshWatcher.inspect_packet(packet)
        reported = self.db.get_auto_reported_nodes()
        self.assertEqual(len(reported), 1)
        self.assertEqual(reported[0]["event_count"], 2)

    def test_normal_hops_no_report(self):
        packet = {
            "fromId": "!goodhop1",
            "from": 222222,
            "hopStart": 3,
            "hopLimit": 2,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "Mensaje limpio"},
        }
        discard = MeshWatcher.inspect_packet(packet)
        self.assertFalse(discard)

        reported = self.db.get_auto_reported_nodes()
        self.assertEqual(len(reported), 0)

    @patch("time.time")
    def test_fast_telemetry_cadence(self, mock_time):
        mock_time.return_value = 1000.0

        packet_telemetry = {
            "fromId": "!fastnode",
            "from": 333333,
            "hopStart": 3,
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {"deviceMetrics": {"batteryLevel": 95, "voltage": 4.12}},
            },
        }

        # Primer paquete (t=1000s): establece la marca de tiempo base
        discard1 = MeshWatcher.inspect_packet(packet_telemetry)
        self.assertFalse(discard1)
        self.assertEqual(len(self.db.get_auto_reported_nodes()), 0)

        # Retransmisión/rebote en menos de 15s (t=1005s): debe ser ignorado silenciosamente
        mock_time.return_value = 1005.0
        MeshWatcher.inspect_packet(packet_telemetry)
        self.assertEqual(len(self.db.get_auto_reported_nodes()), 0)

        # Segundo paquete recibido 120 segundos después (t=1120s): debe saltar infracción limpia
        mock_time.return_value = 1120.0
        discard2 = MeshWatcher.inspect_packet(packet_telemetry)
        self.assertFalse(discard2)

        reported = self.db.get_auto_reported_nodes()
        self.assertEqual(len(reported), 1)
        self.assertEqual(reported[0]["node_id"], "!fastnode")
        self.assertEqual(reported[0]["reason_code"], "FAST_TELEMETRY")
        self.assertEqual(reported[0]["reason_desc"], "Telemetría de batería recibida en 2m")

    @patch("time.time")
    def test_multiple_reasons_for_same_node(self, mock_time):
        mock_time.return_value = 1000.0

        # Infracción 1: Saltos excesivos
        MeshWatcher.inspect_packet({
            "fromId": "!multinode",
            "hopStart": 7,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "H"},
        })

        # Infracción 2: Posición rápida
        MeshWatcher.inspect_packet({
            "fromId": "!multinode",
            "hopStart": 3,
            "decoded": {"portnum": "POSITION_APP", "position": {"latitudeI": 367000000}},
        })
        mock_time.return_value = 1060.0  # 60s después
        MeshWatcher.inspect_packet({
            "fromId": "!multinode",
            "hopStart": 3,
            "decoded": {"portnum": "POSITION_APP", "position": {"latitudeI": 367000000}},
        })

        reported = self.db.get_auto_reported_nodes()
        self.assertEqual(len(reported), 2)
        reason_codes = {r["reason_code"] for r in reported}
        self.assertIn("EXCESSIVE_HOPS", reason_codes)
        self.assertIn("FAST_POSITION", reason_codes)

    def test_local_node_exclusion(self):
        MeshWatcher.set_local_node(node_id="!63ca1feb", node_name="Raupulus PicoBot 2", short_name="RauF")

        # Intentar reportar saltos o telemetría del propio bot -> Debe ser ignorado por completo
        packet = {
            "fromId": "!63ca1feb",
            "hopStart": 7,
            "decoded": {"portnum": "TELEMETRY_APP", "telemetry": {}},
        }
        discard = MeshWatcher.inspect_packet(packet)
        self.assertFalse(discard)

        reported = self.db.get_auto_reported_nodes()
        self.assertEqual(len(reported), 0)

    def test_ignored_node_discard(self):
        node_id = "!spammer99"
        MeshWatcher.set_ignored(node_id, is_ignored=True)
        self.assertTrue(MeshWatcher.is_ignored(node_id))

        # Enviar paquete de nodo ignorado -> debe devolver True (descartar)
        packet = {
            "fromId": node_id,
            "hopStart": 3,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "spam"},
        }
        discard = MeshWatcher.inspect_packet(packet)
        self.assertTrue(discard)

        # Reactivar el nodo
        MeshWatcher.set_ignored(node_id, is_ignored=False)
        self.assertFalse(MeshWatcher.is_ignored(node_id))
        discard = MeshWatcher.inspect_packet(packet)
        self.assertFalse(discard)

    @patch("time.time")
    def test_traceroute_detection_and_abuse(self, mock_time):
        mock_time.return_value = 1000.0
        node_id = "!trace_spammer"

        # 1. Primer traceroute: debe incrementar el contador en nodes a 1 y no generar auto-reporte
        MeshWatcher.inspect_traceroute(node_id)
        node_row = self.db.get_node(node_id)
        self.assertEqual(node_row.get("traces_detected"), 1)
        self.assertEqual(len(self.db.get_auto_reported_nodes()), 0)

        # 2. Segundo traceroute a los 30 segundos (t=1030s, ráfaga >1/min): debe auto-reportar
        mock_time.return_value = 1030.0
        MeshWatcher.inspect_traceroute(node_id)
        node_row = self.db.get_node(node_id)
        self.assertEqual(node_row.get("traces_detected"), 2)

        reported = self.db.get_auto_reported_nodes()
        self.assertEqual(len(reported), 1)
        self.assertEqual(reported[0]["node_id"], node_id)
        self.assertEqual(reported[0]["reason_code"], "EXCESSIVE_TRACES")
        self.assertEqual(reported[0]["reason_desc"], "Spam de traceroutes: 2 peticiones en 1 min")


if __name__ == "__main__":
    unittest.main()
