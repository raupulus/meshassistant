from __future__ import annotations

import unittest
from unittest.mock import MagicMock
from Models.SerialInterface import SerialInterface


class TestReplyId(unittest.TestCase):

    def setUp(self):
        self.serial = SerialInterface.__new__(SerialInterface)
        self.serial.interface = MagicMock()
        self.serial.node_dict = {}

    def test_reply_to_message_channel_without_reply_id(self):
        metadata = {
            "id": 987654,
            "reply_id": 987654,
            "is_direct": False,
            "channel": 2,
            "node_from": {"id": "!node1", "short_name": "N1"},
        }
        res = self.serial.reply_to_message("Respuesta de prueba", metadata)
        self.assertTrue(res)
        self.serial.interface.sendText.assert_called_once_with(
            text="Respuesta de prueba",
            channelIndex=2,
        )

    def test_reply_to_message_direct_with_reply_id(self):
        metadata = {
            "id": 123456,
            "reply_id": 123456,
            "is_direct": True,
            "channel": 0,
            "node_from": {"id": "!node2", "short_name": "N2"},
        }
        res = self.serial.reply_to_message("Privado de prueba", metadata)
        self.assertTrue(res)
        self.serial.interface.sendText.assert_called_once_with(
            text="Privado de prueba",
            destinationId="!node2",
            channelIndex=0,
            replyId=123456,
        )

    def test_reply_to_message_fallback_on_type_error(self):
        # Simular una versión antigua de meshtastic donde sendText no acepta replyId
        def mock_sendText(*args, **kwargs):
            if "replyId" in kwargs:
                raise TypeError("unexpected keyword argument 'replyId'")
            return None

        self.serial.interface.sendText.side_effect = mock_sendText
        metadata = {
            "id": 55555,
            "is_direct": False,
            "channel": 3,
        }
        res = self.serial.reply_to_message("Fallback prueba", metadata)
        self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()
