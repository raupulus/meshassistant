import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from create_db import ensure_database
from Models.Database import Database
from Models.PacketSniffer import PacketSniffer


class TestPacketSniffer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_sniffer.sql"
        ensure_database(self.db_path)
        self.db = Database(db_path=self.db_path)
        # Limpiar caché interno de PacketSniffer
        PacketSniffer._rules_cache = []
        PacketSniffer._captured_nodes_cache = set()
        PacketSniffer._last_cache_time = 0.0
        PacketSniffer._recent_packet_ids.clear()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rule_validation_to_or_from_required(self):
        """Valida que to o from sea obligatorio al crear una regla."""
        with self.assertRaises(ValueError):
            self.db.save_capture_rule(to_node_id=None, from_node_id=None)

        with self.assertRaises(ValueError):
            self.db.save_capture_rule(to_node_id="", from_node_id="   ")

    def test_rule_admin_pki_forces_full_encrypted_payload(self):
        """Si el canal es admin_pki, se fuerza save_payload_mode = 'full_encrypted'."""
        rule_id = self.db.save_capture_rule(
            name="Test Admin PKI",
            to_node_id="!12345678",
            channel_filter="admin_pki",
            save_payload_mode="text_if_available",
        )
        rules = self.db.get_capture_rules()
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["id"], rule_id)
        self.assertEqual(rules[0]["channel_filter"], "admin_pki")
        self.assertEqual(rules[0]["save_payload_mode"], "full_encrypted")

    def test_rule_crud_operations(self):
        """Prueba inserción, toggle y eliminación de reglas."""
        r1 = self.db.save_capture_rule(
            name="Regla 1",
            from_node_id="!aabbccdd",
            channel_filter="all",
            only_encrypted=True,
        )
        rules = self.db.get_capture_rules(active_only=True)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["only_encrypted"], 1)

        # Desactivar regla
        self.db.toggle_capture_rule(r1, False)
        active_rules = self.db.get_capture_rules(active_only=True)
        self.assertEqual(len(active_rules), 0)
        all_rules = self.db.get_capture_rules(active_only=False)
        self.assertEqual(len(all_rules), 1)

        # Eliminar regla
        deleted = self.db.delete_capture_rule(r1)
        self.assertTrue(deleted)
        self.assertEqual(len(self.db.get_capture_rules()), 0)

    def test_node_captured_marking(self):
        """Prueba marcar un nodo como capturado y consultarlo."""
        node_id = "!router99"
        self.db.create_node_if_not_exists(node_id)
        self.db.set_node_captured(node_id, is_captured=True, criteria='{"save":"all"}')

        nodes = self.db.get_all_nodes()
        match = next((n for n in nodes if n["node_id"] == node_id), None)
        self.assertIsNotNone(match)
        self.assertEqual(match.get("is_captured"), 1)
        self.assertEqual(match.get("capture_criteria"), '{"save":"all"}')

    def test_inspect_packet_matching_rule(self):
        """Prueba captura de paquetes que coinciden con una regla."""
        self.db.save_capture_rule(
            name="Vigilancia Router 1",
            from_node_id="!11223344",
            channel_filter="all",
            save_payload_mode="full_encrypted",
        )

        with patch("Models.PacketSniffer.Database", return_value=self.db), \
             patch("Models.EventBroadcaster.broadcast_event") as mock_broadcast:

            PacketSniffer.reload_rules()

            # Paquete 1: viene de otro nodo (no debe capturarse)
            pkt_other = {
                "id": 1001,
                "from": 0x99999999,
                "fromId": "!99999999",
                "to": 0xFFFFFFFF,
                "toId": "^all",
                "channel": 0,
                "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "Hola"},
            }
            captured = PacketSniffer.inspect_packet(pkt_other)
            self.assertFalse(captured)
            self.assertEqual(self.db.count_captured_packets(), 0)

            # Paquete 2: viene del nodo vigilado (!11223344)
            pkt_target = {
                "id": 1002,
                "from": 0x11223344,
                "fromId": "!11223344",
                "to": 0x12345678,
                "toId": "!12345678",
                "channel": 0,
                "encrypted": b"\x01\x02\x03\x04\xaa\xbb\xcc",
                "rxTime": 1720000000,
                "rxSnr": 8.5,
                "rxRssi": -65,
                "hopLimit": 2,
                "hopStart": 3,
                "wantAck": True,
            }
            captured2 = PacketSniffer.inspect_packet(pkt_target)
            self.assertTrue(captured2)
            self.assertEqual(self.db.count_captured_packets(), 1)

            # Comprobar registro guardado
            pkts = self.db.get_captured_packets()
            self.assertEqual(len(pkts), 1)
            p = pkts[0]
            self.assertEqual(p["from_id"], "!11223344")
            self.assertEqual(p["to_id"], "!12345678")
            self.assertEqual(p["is_encrypted"], 1)
            self.assertEqual(p["is_admin_pki"], 1)  # Ch 0 unicast
            self.assertEqual(p["payload_hex"], "01020304aabbcc")
            self.assertEqual(p["payload_size"], 7)
            self.assertEqual(p["hops"], 1)  # hopStart 3 - hopLimit 2
            self.assertEqual(p["want_ack"], 1)

            # Comprobar emisión por IPC
            mock_broadcast.assert_called_once()
            args, kwargs = mock_broadcast.call_args
            self.assertEqual(args[0], "packet_captured")
            self.assertEqual(args[1]["from_id"], "!11223344")

    def test_inspect_packet_admin_pki_filtering(self):
        """Prueba que una regla de canal 'admin_pki' solo captura unicast en canal 0."""
        self.db.save_capture_rule(
            name="Admin PKI Only",
            to_node_id="!12345678",
            channel_filter="admin_pki",
        )

        with patch("Models.PacketSniffer.Database", return_value=self.db), \
             patch("Models.EventBroadcaster.broadcast_event"):

            PacketSniffer.reload_rules()

            # Broadcast hacia ^all en canal 0 (NO debe capturarse como Admin PKI)
            pkt_bcast = {
                "id": 2001,
                "from": 0x12345678,
                "to": 0xFFFFFFFF,
                "toId": "^all",
                "channel": 0,
            }
            self.assertFalse(PacketSniffer.inspect_packet(pkt_bcast))

            # Unicast en canal 1 hacia el nodo (NO debe capturarse porque no es canal 0)
            pkt_ch1 = {
                "id": 2002,
                "from": 0x99999999,
                "to": 0x12345678,
                "toId": "!12345678",
                "channel": 1,
            }
            self.assertFalse(PacketSniffer.inspect_packet(pkt_ch1))

            # Unicast en canal 0 hacia el nodo (SÍ debe capturarse)
            pkt_pki = {
                "id": 2003,
                "from": 0x99999999,
                "to": 0x12345678,
                "toId": "!12345678",
                "channel": 0,
                "pki_encrypted": b"\xff\xee\xdd",
            }
            self.assertTrue(PacketSniffer.inspect_packet(pkt_pki))
            self.assertEqual(self.db.count_captured_packets(), 1)

    def test_clear_captured_packets(self):
        """Prueba limpiar la tabla de paquetes capturados."""
        self.db.insert_captured_packet({
            "from_id": "!11111111",
            "to_id": "!22222222",
            "channel": 0,
            "payload_size": 10,
        })
        self.db.insert_captured_packet({
            "from_id": "!33333333",
            "to_id": "!44444444",
            "channel": 0,
            "payload_size": 20,
        })
        self.assertEqual(self.db.count_captured_packets(), 2)

        cleared = self.db.clear_captured_packets()
        self.assertEqual(cleared, 2)
        self.assertEqual(self.db.count_captured_packets(), 0)

    def test_update_captured_packet_note(self):
        """Prueba añadir, actualizar y borrar notas en un paquete capturado."""
        pkt_id = self.db.insert_captured_packet({
            "from_id": "!12345678",
            "to_id": "!87654321",
            "channel": 0,
            "payload_size": 15,
        })
        # Inicialmente sin nota
        p = self.db.get_captured_packet_by_id(pkt_id)
        self.assertIsNone(p.get("note"))

        # Añadir nota
        ok = self.db.update_captured_packet_note(pkt_id, "Paquete sospechoso de router norte")
        self.assertTrue(ok)
        p = self.db.get_captured_packet_by_id(pkt_id)
        self.assertEqual(p.get("note"), "Paquete sospechoso de router norte")

        # Verificar que get_captured_packets también incluye la nota
        pkts = self.db.get_captured_packets(limit=10)
        self.assertEqual(len(pkts), 1)
        self.assertEqual(pkts[0].get("note"), "Paquete sospechoso de router norte")

        # Actualizar nota
        self.db.update_captured_packet_note(pkt_id, "Confirmado: es telemetría estándar")
        p = self.db.get_captured_packet_by_id(pkt_id)
        self.assertEqual(p.get("note"), "Confirmado: es telemetría estándar")

        # Borrar nota (None)
        self.db.update_captured_packet_note(pkt_id, None)
        p = self.db.get_captured_packet_by_id(pkt_id)
        self.assertIsNone(p.get("note"))

    def test_edit_existing_capture_rule(self):
        """Prueba editar una regla de captura existente reutilizando su ID."""
        rule_id = self.db.save_capture_rule(
            name="Regla Inicial",
            to_node_id="!11111111",
            channel_filter="all",
            only_encrypted=False,
            save_payload_mode="full_encrypted",
        )
        rules = self.db.get_capture_rules()
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["name"], "Regla Inicial")
        self.assertEqual(rules[0]["channel_filter"], "all")
        self.assertEqual(rules[0]["only_encrypted"], 0)

        # Modificar la regla existente
        updated_id = self.db.save_capture_rule(
            rule_id=rule_id,
            name="Regla Editada Router 2",
            to_node_id="!22222222",
            channel_filter="admin_pki",
            only_encrypted=True,
            save_payload_mode="text_if_available",  # En admin_pki se debe forzar a full_encrypted
        )
        self.assertEqual(updated_id, rule_id)

        # Verificar que se actualizó en la BD y no se creó un duplicado
        rules = self.db.get_capture_rules()
        self.assertEqual(len(rules), 1)
        r = rules[0]
        self.assertEqual(r["id"], rule_id)
        self.assertEqual(r["name"], "Regla Editada Router 2")
        self.assertEqual(r["to_node_id"], "!22222222")
        self.assertEqual(r["channel_filter"], "admin_pki")
        self.assertEqual(r["only_encrypted"], 1)
        self.assertEqual(r["save_payload_mode"], "full_encrypted")

    def test_delete_captured_packet(self):
        """Prueba eliminar un paquete capturado individualmente por su ID."""
        pkt1 = self.db.insert_captured_packet({
            "from_id": "!11111111",
            "to_id": "!22222222",
            "channel": 0,
            "payload_size": 10,
        })
        pkt2 = self.db.insert_captured_packet({
            "from_id": "!33333333",
            "to_id": "!44444444",
            "channel": 1,
            "payload_size": 25,
        })
        self.assertEqual(self.db.count_captured_packets(), 2)

        # Eliminar paquete 1
        ok = self.db.delete_captured_packet(pkt1)
        self.assertTrue(ok)
        self.assertEqual(self.db.count_captured_packets(), 1)
        self.assertIsNone(self.db.get_captured_packet_by_id(pkt1))
        self.assertIsNotNone(self.db.get_captured_packet_by_id(pkt2))

        # Intentar eliminar de nuevo o ID inexistente devuelve False
        self.assertFalse(self.db.delete_captured_packet(pkt1))
        self.assertFalse(self.db.delete_captured_packet(999999))


if __name__ == "__main__":
    unittest.main()
