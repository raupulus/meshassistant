from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import tempfile
import unittest
import urllib.request
from typing import Any, Dict

from Services.Gateway import GatewayService


class MockConnection:
    pass


class MockRequest:
    def __init__(self, path: str, headers: Dict[str, str] | None = None):
        self.path = path
        self.headers = headers or {}


class TestGatewayHttp(unittest.IsolatedAsyncioTestCase):
    """Pruebas unitarias para el servidor HTTP estático integrado en GatewayService."""

    def setUp(self):
        self.gateway = GatewayService(host="127.0.0.1", port=8691)

    def test_serve_index_html(self):
        """Verifica que GET / retorna index.html con código 200."""
        req = MockRequest(path="/")
        resp = self.gateway._process_http_request(MockConnection(), req)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Meshassistant", resp.body)
        self.assertEqual(resp.headers.get("Content-Type"), "text/html; charset=utf-8")

    def test_serve_app_js(self):
        """Verifica que GET /app.js retorna el archivo JS con el Content-Type correcto."""
        req = MockRequest(path="/app.js")
        resp = self.gateway._process_http_request(MockConnection(), req)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"MeshDashboard", resp.body)
        self.assertEqual(resp.headers.get("Content-Type"), "application/javascript; charset=utf-8")

    def test_serve_style_css(self):
        """Verifica que GET /style.css retorna el archivo CSS con el Content-Type correcto."""
        req = MockRequest(path="/style.css")
        resp = self.gateway._process_http_request(MockConnection(), req)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"--bg-main", resp.body)
        self.assertEqual(resp.headers.get("Content-Type"), "text/css; charset=utf-8")

    def test_404_on_missing_file(self):
        """Verifica que archivos inexistentes retornan HTTP 404."""
        req = MockRequest(path="/archivo_inexistente.html")
        resp = self.gateway._process_http_request(MockConnection(), req)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 404)

    def test_directory_traversal_prevention(self):
        """Verifica que intentos de path traversal retornan 404 y no exponen archivos fuera de web/."""
        req = MockRequest(path="/../main.py")
        resp = self.gateway._process_http_request(MockConnection(), req)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 404)

    def test_websocket_upgrade_bypass(self):
        """Verifica que las peticiones con Upgrade: websocket retornan None para completar el handshake."""
        req = MockRequest(path="/", headers={"Upgrade": "websocket"})
        resp = self.gateway._process_http_request(MockConnection(), req)
        self.assertIsNone(resp)


class TestGatewayHttpLive(unittest.IsolatedAsyncioTestCase):
    """Pruebas de integración HTTP en vivo con socket TCP real."""

    async def test_live_http_request(self):
        """Levanta GatewayService y hace una petición HTTP GET real con urllib."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_socket_path = os.path.join(tmpdir, "gw_http_live.sock")
            test_port = 8696

            gateway = GatewayService(
                host="127.0.0.1",
                port=test_port,
                socket_path=test_socket_path,
            )

            server_task = asyncio.create_task(gateway.start())
            await asyncio.sleep(0.1)

            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                res_bytes = await loop.run_in_executor(
                    pool,
                    lambda: urllib.request.urlopen(f"http://127.0.0.1:{test_port}/").read()
                )

            self.assertIn(b"Meshassistant", res_bytes)
            self.assertIn(b"app.js", res_bytes)

            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    unittest.main()
