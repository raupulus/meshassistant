from __future__ import annotations

import asyncio
import json
import os
import socket
import tempfile
import unittest
from typing import Any, Dict

import websockets

from Models.EventBroadcaster import EventBroadcaster, broadcast_event
from Services.Gateway import GatewayService, MAX_RECENT_MESSAGES
from create_db import ensure_database


class TestEventBroadcaster(unittest.TestCase):
    """Pruebas unitarias para el emisor IPC EventBroadcaster."""

    def test_broadcast_without_server(self):
        """Verifica que emitir sin servidor activo retorna False sin lanzar excepción."""
        eb = EventBroadcaster(socket_path="/tmp/non_existent_socket_test.sock")
        result = eb.broadcast("test_event", {"test": 123})
        self.assertFalse(result)

    def test_broadcast_with_receiver(self):
        """Verifica que un receptor Unix DGRAM recibe el datagrama JSON con formato estándar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sock_path = os.path.join(tmpdir, "test_events.sock")
            rx_sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            rx_sock.bind(sock_path)

            try:
                eb = EventBroadcaster(socket_path=sock_path)
                data_payload = {"msg": "Hola", "channel": 0, "from": "!12345678"}
                sent = eb.broadcast("message_rx", data_payload)
                self.assertTrue(sent)

                raw_bytes, _ = rx_sock.recvfrom(4096)
                received_obj = json.loads(raw_bytes.decode("utf-8"))

                self.assertEqual(received_obj.get("event"), "message_rx")
                self.assertIn("ts", received_obj)
                self.assertEqual(received_obj.get("data"), data_payload)
            finally:
                rx_sock.close()
                eb.close()

    def test_singleton_instance(self):
        """Verifica que get_instance retorna siempre el mismo objeto."""
        inst1 = EventBroadcaster.get_instance()
        inst2 = EventBroadcaster.get_instance()
        self.assertIs(inst1, inst2)


class TestGatewayService(unittest.IsolatedAsyncioTestCase):
    """Pruebas unitarias y de integración para GatewayService."""

    def setUp(self):
        ensure_database()
        self.gateway = GatewayService(host="127.0.0.1", port=8689)

    def test_ipc_event_updates_ram_buffers(self):
        """Verifica que los eventos IPC actualizan el ring buffer y estados en memoria RAM."""
        # 1. Mensaje de texto (ring buffer)
        msg_event = {
            "event": "message_rx",
            "ts": "2026-08-21T20:00:00",
            "data": {"text": "Mensaje de prueba", "channel": 0},
        }
        self.gateway.on_ipc_event(msg_event)
        self.assertEqual(len(self.gateway.recent_messages), 1)
        self.assertEqual(self.gateway.recent_messages[0], msg_event)

        # 2. System status
        status_event = {
            "event": "system_status",
            "ts": "2026-08-21T20:00:01",
            "data": {"uart_connected": True, "nodes_in_memory": 5},
        }
        self.gateway.on_ipc_event(status_event)
        self.assertEqual(self.gateway.last_system_status, status_event["data"])

        # 3. Local node info
        node_event = {
            "event": "local_node_info",
            "ts": "2026-08-21T20:00:02",
            "data": {"my_node_id": "!testnode", "region": "EU_868"},
        }
        self.gateway.on_ipc_event(node_event)
        self.assertEqual(self.gateway.last_local_node, node_event["data"])

    async def test_handle_actions(self):
        """Verifica el despacho y respuestas de todas las acciones del Contrato de API."""
        mock_ws = None  # No necesario para llamadas directas a _handle_action

        # 1. get_snapshot
        resp = await self.gateway._handle_action(mock_ws, {
            "action": "get_snapshot",
            "req_id": "req_01",
            "params": {"include": ["recent_messages", "system_status", "nodes"]},
        })
        self.assertTrue(resp["success"])
        self.assertEqual(resp["action"], "get_snapshot")
        self.assertEqual(resp["req_id"], "req_01")
        self.assertIn("recent_messages", resp["data"])
        self.assertIn("system_status", resp["data"])
        self.assertIn("nodes", resp["data"])

        # 2. request_trace
        resp_trace = await self.gateway._handle_action(mock_ws, {
            "action": "request_trace",
            "req_id": "req_02",
            "params": {"dest": "!testdestination"},
        })
        self.assertTrue(resp_trace["success"])
        self.assertEqual(resp_trace["data"]["status"], "queued")
        self.assertIsInstance(resp_trace["data"]["trace_id"], int)

        # 3. request_trace sin destino (error esperado)
        resp_err = await self.gateway._handle_action(mock_ws, {
            "action": "request_trace",
            "req_id": "req_03",
            "params": {},
        })
        self.assertFalse(resp_err["success"])
        self.assertIsNotNone(resp_err["error"])

        # 4. set_node_favorite
        resp_fav = await self.gateway._handle_action(mock_ws, {
            "action": "set_node_favorite",
            "req_id": "req_04",
            "params": {"node_id": "!testdestination", "is_favorite": True},
        })
        self.assertTrue(resp_fav["success"])
        self.assertTrue(resp_fav["data"]["is_favorite"])

        # 5. get_weather y get_tides
        resp_w = await self.gateway._handle_action(mock_ws, {"action": "get_weather"})
        self.assertTrue(resp_w["success"])
        resp_t = await self.gateway._handle_action(mock_ws, {"action": "get_tides"})
        self.assertTrue(resp_t["success"])

        # 6. Acción desconocida
        resp_unk = await self.gateway._handle_action(mock_ws, {"action": "invalid_action"})
        self.assertFalse(resp_unk["success"])
        self.assertIn("desconocida", resp_unk["error"].lower())


class TestGatewayIntegration(unittest.IsolatedAsyncioTestCase):
    """Pruebas de integración en vivo con servidor WebSocket y cliente real."""

    async def test_full_websocket_and_ipc_cycle(self):
        """Levanta el Gateway, conecta un cliente WebSocket real y valida la recepción de eventos IPC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_socket_path = os.path.join(tmpdir, "gw_test_events.sock")
            test_port = 8695

            gateway = GatewayService(
                host="127.0.0.1",
                port=test_port,
                socket_path=test_socket_path,
            )

            # Iniciar servidor gateway en background
            server_task = asyncio.create_task(gateway.start())
            await asyncio.sleep(0.1)  # Margen para bind

            ws_url = f"ws://127.0.0.1:{test_port}"
            try:
                async with websockets.connect(ws_url) as ws:
                    # 1. Recibir mensaje de bienvenida
                    welcome_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    welcome_obj = json.loads(welcome_raw)
                    self.assertEqual(welcome_obj.get("event"), "welcome")
                    self.assertEqual(welcome_obj["data"]["server"], "meshassistant-gateway")

                    # 2. Emitir evento IPC desde EventBroadcaster y comprobar recepción push
                    eb = EventBroadcaster(socket_path=test_socket_path)
                    payload = {"from": "!12345678", "text": "Hola integracion", "channel": 0}
                    eb.broadcast("message_rx", payload)

                    event_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    event_obj = json.loads(event_raw)
                    self.assertEqual(event_obj.get("event"), "message_rx")
                    self.assertEqual(event_obj["data"]["text"], "Hola integracion")

                    # 3. Enviar acción get_snapshot por WebSocket y validar respuesta
                    req = {
                        "action": "get_snapshot",
                        "req_id": "snap_live_01",
                        "params": {"include": ["recent_messages", "stats"]},
                    }
                    await ws.send(json.dumps(req))

                    resp_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    resp_obj = json.loads(resp_raw)
                    self.assertEqual(resp_obj.get("type"), "response")
                    self.assertEqual(resp_obj.get("req_id"), "snap_live_01")
                    self.assertTrue(resp_obj.get("success"))
                    self.assertIn("recent_messages", resp_obj.get("data", {}))
            finally:
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass


if __name__ == "__main__":
    unittest.main()
