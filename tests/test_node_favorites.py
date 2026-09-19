import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from create_db import ensure_database
from Models.Database import Database
from Models.Node import Node
from Models.SerialInterface import SerialInterface


class TestNodeFavorites(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_fav.sql"
        ensure_database(self.db_path)
        self.db = Database(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_radio_packet_does_not_clear_user_favorite(self):
        node_id = "!candidato05"
        self.db.create_node_if_not_exists(node_id)
        # Usuario marca el nodo como favorito en la web/BD
        self.db.update_node(node_id, {
            "name": "Candidato05",
            "short_name": "CC05",
            "is_favorite": True,
        })

        node_data = self.db.get_node(node_id)
        self.assertEqual(node_data.get("is_favorite"), 1)

        # Se instancia el nodo (como hace main.py o al recibir un paquete)
        with patch("Models.Node.Database", return_value=self.db):
            node = Node(node_id)
            self.assertTrue(node.is_favorite)

            # Llega un paquete NODEINFO de la malla sin el campo is_favorite
            node.update_metadata({
                "name": "Candidato05",
                "short_name": "CC05",
                "snr": 11.5,
                "rssi": -45,
                "battery": 80,
                "voltage": 3.95,
            })

            # Comprobar que en memoria y en BD sigue siendo favorito (1)
            self.assertTrue(node.is_favorite)
            updated_data = self.db.get_node(node_id)
            self.assertEqual(updated_data.get("is_favorite"), 1)

            # Llega un paquete de radio con is_favorite=None o isFavorite=False (como en protobuf)
            node.update_metadata({
                "snr": 12.0,
                "is_favorite": None,
                "isFavorite": False,
            })

            self.assertTrue(node.is_favorite)
            updated_data2 = self.db.get_node(node_id)
            self.assertEqual(updated_data2.get("is_favorite"), 1)

    def test_explicit_unfavorite_works(self):
        node_id = "!candidato05"
        self.db.create_node_if_not_exists(node_id)
        self.db.update_node(node_id, {"is_favorite": True})
        self.assertEqual(self.db.get_node(node_id).get("is_favorite"), 1)

        # Usuario desmarca favorito
        self.db.update_node(node_id, {"is_favorite": False})
        self.assertEqual(self.db.get_node(node_id).get("is_favorite"), 0)

        # Un nuevo paquete de radio no lo vuelve a marcar como favorito
        with patch("Models.Node.Database", return_value=self.db):
            node = Node(node_id)
            self.assertFalse(node.is_favorite)
            node.update_metadata({"snr": 9.5})
            self.assertEqual(self.db.get_node(node_id).get("is_favorite"), 0)

    def test_get_nodes_info_does_not_overwrite_db_favorite(self):
        node_id = "!16cd4834"
        self.db.create_node_if_not_exists(node_id)
        self.db.update_node(node_id, {"name": "Candidato05", "is_favorite": True})

        with patch("Models.Database.Database", return_value=self.db), \
             patch("Models.Node.Database", return_value=self.db):
            mock_interface = MagicMock()
            mock_interface.nodes = {
                node_id: {
                    "num": 382552116,
                    "user": {"id": node_id, "longName": "Candidato05", "shortName": "CC05"},
                    "snr": 11.5,
                    "isFavorite": False,  # La radio física no lo tiene en favoritos
                }
            }

            serial_mock = SerialInterface(serial_port="/dev/null")
            serial_mock.interface = mock_interface
            serial_mock.get_nodes()

            # El nodo debe seguir siendo favorito en BD
            node_in_db = self.db.get_node(node_id)
            self.assertEqual(node_in_db.get("is_favorite"), 1)
            self.assertTrue(serial_mock.node_dict[node_id].is_favorite)


if __name__ == "__main__":
    unittest.main()
