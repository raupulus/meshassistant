from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import time
import Commands.ia as ia_module
import env


class DummyInterface:
    def __init__(self):
        self.replies = []

    def reply_to_message(self, text, metadata):
        self.replies.append({"text": text, "metadata": metadata})


class TestIaCommand(unittest.TestCase):

    def setUp(self):
        self.interface = DummyInterface()
        self.metadata = {
            "node_from": {"id": "!testnode", "short_name": "Test"},
            "channel": 0,
            "is_direct": True,
        }
        # Vaciar la cola si tuviera elementos residuales
        while not ia_module._ia_queue.empty():
            try:
                ia_module._ia_queue.get_nowait()
                ia_module._ia_queue.task_done()
            except Exception:
                break

    def test_ia_help_and_empty(self):
        # Sin argumentos
        ia_module.ia_callback(self.interface, [], "/ia", self.metadata)
        self.assertEqual(len(self.interface.replies), 1)
        self.assertIn("Uso: !ia", self.interface.replies[0]["text"])

        # Con argumento help
        self.interface.replies.clear()
        ia_module.ia_callback(self.interface, ["help"], "/ia help", self.metadata)
        self.assertEqual(len(self.interface.replies), 1)
        self.assertIn("Uso: !ia", self.interface.replies[0]["text"])

    def test_ia_disabled(self):
        orig_enabled = getattr(env, "IA_API_ENABLED", True)
        try:
            env.IA_API_ENABLED = False
            ia_module.ia_callback(self.interface, ["picadura", "medusa"], "/ia picadura medusa", self.metadata)
            self.assertEqual(len(self.interface.replies), 1)
            self.assertIn("no está habilitado", self.interface.replies[0]["text"])
        finally:
            env.IA_API_ENABLED = orig_enabled

    @patch("requests.post")
    def test_ia_successful_query(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "mensajes": ["Lava con agua de mar. No frotes. Info orientativa. Llama al 112."],
            "categoria": "fauna",
            "confianza": 0.75,
            "tiempo_ms": 1500,
            "modelo": "qwen",
        }
        mock_post.return_value = mock_response

        orig_enabled = getattr(env, "IA_API_ENABLED", True)
        env.IA_API_ENABLED = True
        try:
            ia_module.ia_callback(self.interface, ["picadura", "medusa"], "/ia picadura medusa", self.metadata)
            # Esperar a que el worker procese la cola
            ia_module._ia_queue.join()

            self.assertEqual(len(self.interface.replies), 1)
            self.assertEqual(self.interface.replies[0]["text"], "Lava con agua de mar. No frotes. Info orientativa. Llama al 112.")
            self.assertTrue(mock_post.called)
            args, kwargs = mock_post.call_args
            self.assertIn("/v1/consulta", args[0])
            self.assertEqual(kwargs["json"]["consulta"], "picadura medusa")
            self.assertEqual(kwargs["json"]["id_conversacion"], "meshtastic:!testnode")
        finally:
            env.IA_API_ENABLED = orig_enabled

    @patch("requests.post")
    @patch("time.sleep", return_value=None)
    def test_ia_multiple_parts_query(self, mock_sleep, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "mensajes": [
                "Parte 1: Medidas iniciales para la picadura.",
                "Parte 2: Aplicar calor local. Info orientativa. Llama al 112."
            ],
            "categoria": "fauna",
            "tiempo_ms": 2000,
        }
        mock_post.return_value = mock_response

        orig_enabled = getattr(env, "IA_API_ENABLED", True)
        env.IA_API_ENABLED = True
        try:
            ia_module.ia_callback(self.interface, ["picadura", "pez", "arana"], "/ia picadura pez arana", self.metadata)
            ia_module._ia_queue.join()

            self.assertEqual(len(self.interface.replies), 2)
            self.assertEqual(self.interface.replies[0]["text"], "Parte 1: Medidas iniciales para la picadura.")
            self.assertEqual(self.interface.replies[1]["text"], "Parte 2: Aplicar calor local. Info orientativa. Llama al 112.")
            # Debe haber dormido entre partes
            mock_sleep.assert_called_with(3.0)
        finally:
            env.IA_API_ENABLED = orig_enabled

    @patch("requests.post")
    def test_ia_reset_conversation(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "mensaje": "Conversación reseteada correctamente."}
        mock_post.return_value = mock_response

        orig_enabled = getattr(env, "IA_API_ENABLED", True)
        env.IA_API_ENABLED = True
        try:
            ia_module.ia_callback(self.interface, ["reset"], "/ia reset", self.metadata)
            ia_module._ia_queue.join()

            self.assertEqual(len(self.interface.replies), 1)
            self.assertIn("reiniciada", self.interface.replies[0]["text"])
            self.assertTrue(mock_post.called)
            args, kwargs = mock_post.call_args
            self.assertIn("/v1/conversacion/reset", args[0])
            self.assertEqual(kwargs["json"]["id_conversacion"], "meshtastic:!testnode")
        finally:
            env.IA_API_ENABLED = orig_enabled

    @patch("requests.post", side_effect=Exception("Connection refused"))
    def test_ia_server_unavailable_error(self, mock_post):
        orig_enabled = getattr(env, "IA_API_ENABLED", True)
        env.IA_API_ENABLED = True
        try:
            ia_module.ia_callback(self.interface, ["que", "hacer", "en", "niebla"], "/ia que hacer en niebla", self.metadata)
            ia_module._ia_queue.join()

            self.assertEqual(len(self.interface.replies), 1)
            self.assertEqual(
                self.interface.replies[0]["text"],
                "Servidor IA de @raupulus no disponible en este momento."
            )
        finally:
            env.IA_API_ENABLED = orig_enabled

    def test_ia_channel_filtering(self):
        orig_enabled = getattr(env, "IA_API_ENABLED", True)
        orig_channels = getattr(env, "IA_CHANNELS", ['raupulus'])
        env.IA_API_ENABLED = True
        env.IA_CHANNELS = ['raupulus']
        try:
            # 1. En canal público no autorizado (canal 0: SFNarrow) -> NO debe responder
            meta_ch0 = {
                "node_from": {"id": "!user0", "short_name": "U0"},
                "channel": 0,
                "is_direct": False,
            }
            ia_module.ia_callback(self.interface, ["help"], "/ia help", meta_ch0)
            self.assertEqual(len(self.interface.replies), 0, "No debe responder en canal 0 no autorizado")

            # 2. En canal público autorizado (canal 6: raupulus) -> SÍ debe responder
            meta_ch6 = {
                "node_from": {"id": "!user6", "short_name": "U6"},
                "channel": 6,
                "is_direct": False,
            }
            ia_module.ia_callback(self.interface, ["help"], "/ia help", meta_ch6)
            self.assertEqual(len(self.interface.replies), 1, "Debe responder en canal 6 autorizado")

            # 3. En mensaje directo privado (is_direct = True) en cualquier canal -> SÍ debe responder
            self.interface.replies.clear()
            meta_direct = {
                "node_from": {"id": "!user_dm", "short_name": "UDM"},
                "channel": 0,
                "is_direct": True,
            }
            ia_module.ia_callback(self.interface, ["help"], "/ia help", meta_direct)
            self.assertEqual(len(self.interface.replies), 1, "Debe responder siempre en privado")
        finally:
            env.IA_API_ENABLED = orig_enabled
            env.IA_CHANNELS = orig_channels


if __name__ == "__main__":
    unittest.main()
