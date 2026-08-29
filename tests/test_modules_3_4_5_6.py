import unittest
import os
import sys
import shutil
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from create_db import ensure_database
from Models.Database import Database
from functions import get_system_telemetry, split_messages, MESH_MAX_BYTES
from Models.Bulletin import BulletinGenerator
from Models.AntiAbuse import AntiAbuseManager
from Commands.estado import estado_callback
from Commands.stats import stats_callback


class MockInterface:
    def __init__(self):
        self.replies = []
        self.sent = []
        self.interface = None

    def reply_to_message(self, text, metadata=None):
        self.replies.append((text, metadata))

    def send(self, text, dest="^all", channel=0):
        self.sent.append((text, dest, channel))


class TestModules(unittest.TestCase):
    def setUp(self):
        ensure_database()
        self.db = Database()

    def test_system_telemetry(self):
        telem = get_system_telemetry()
        self.assertIn("cpu_temp", telem)
        self.assertIn("load_1m", telem)
        self.assertIn("ram_percent", telem)
        self.assertIn("disk_free_gb", telem)
        self.assertIn("system_uptime_seconds", telem)
        print("Telemetry extracted:", telem)

    def test_scheduled_messages_crud(self):
        # Create
        msg_id = self.db.create_scheduled_message(
            message="Test broadcast every 2h",
            channels=[0, 6],
            period_type="hours",
            period_value=2,
            start_at=datetime.now().isoformat(),
            enabled=1,
        )
        self.assertIsNotNone(msg_id)

        # Get
        m = self.db.get_scheduled_message(msg_id)
        self.assertIsNotNone(m)
        self.assertEqual(m["message"], "Test broadcast every 2h")
        self.assertEqual(m["enabled"], 1)

        # Pending check
        pending = self.db.get_pending_scheduled_messages()
        pending_ids = [p["id"] for p in pending]
        self.assertIn(msg_id, pending_ids)

        # Mark sent
        next_run = (datetime.now() + timedelta(hours=2)).isoformat()
        self.db.mark_scheduled_message_sent(msg_id, next_run_at=next_run)
        m_after = self.db.get_scheduled_message(msg_id)
        self.assertIsNotNone(m_after["last_sent_at"])
        self.assertEqual(m_after["next_run_at"], next_run)

        # Delete
        self.db.delete_scheduled_message(msg_id)
        self.assertIsNone(self.db.get_scheduled_message(msg_id))

    def test_blocked_nodes_and_antiabuse(self):
        mgr = AntiAbuseManager()
        test_node = "!test_node_99"

        # Initially allowed
        allowed, reason = mgr.is_allowed(test_node, command="ping", node_name="Tester")
        self.assertTrue(allowed)

        # Manual block
        self.db.block_node(test_node, node_name="Tester", block_type="manual", reason="Spam")
        self.assertTrue(self.db.is_node_blocked(test_node)[0])

        allowed, reason = mgr.is_allowed(test_node, command="ping", node_name="Tester")
        self.assertFalse(allowed)
        self.assertEqual(reason, "Spam")

        # Unblock
        self.db.unblock_node(test_node)
        self.assertFalse(self.db.is_node_blocked(test_node)[0])

        # Test rate limiter burst (> 10 cmds in window)
        flood_node = "!flood_node_1"
        for i in range(10):
            ok, _ = mgr.is_allowed(flood_node, command="ping")
            self.assertTrue(ok)

        # 11th command triggers rate limit ban
        ok11, r11 = mgr.is_allowed(flood_node, command="ping")
        self.assertFalse(ok11)
        self.assertTrue(self.db.is_node_blocked(flood_node)[0])
        
        # Clean up
        self.db.unblock_node(flood_node)

    def test_scheduled_dynamic_command_execution(self):
        from data import commands_dict
        from functions import search_command

        cmd, args = search_command("/estado")
        self.assertEqual(cmd, "estado")
        self.assertIn(cmd, commands_dict)

        # Mock capturing interface
        class MockScheduledCapture:
            def __init__(self):
                self.captured = []

            def reply_to_message(self, text, metadata=None, reply_id=None):
                if text:
                    self.captured.append(text)

            def send(self, text, dest="^all", channel=0):
                if text:
                    self.captured.append(text)

        cap = MockScheduledCapture()
        metadata = {
            "node_from": {"id": "!SCHEDULED", "name": "Programador"},
            "node_to": "^all",
            "channel": 4,
            "is_direct": True,
            "is_scheduled": True,
        }

        commands_dict[cmd]["callback"](cap, args, "/estado", metadata)
        self.assertGreaterEqual(len(cap.captured), 1)
        self.assertIn("Bot", cap.captured[0])
        print("Captured scheduled command output:", cap.captured)

    def test_bulletin_generator(self):
        parts = BulletinGenerator.build_bulletin(slot_name="Matinal")
        self.assertIsInstance(parts, list)
        self.assertTrue(len(parts) >= 1)
        for p in parts:
            self.assertLessEqual(len(p.encode("utf-8")), MESH_MAX_BYTES)
            print("Bulletin part:", p)

    def test_boletin_callback(self):
        from Commands.boletin import boletin_callback
        mock_if = MockInterface()
        boletin_callback(mock_if, ["vespertino"], "/boletin vespertino", {"channel": 6, "is_direct": False})
        self.assertGreaterEqual(len(mock_if.replies), 1)
        first_reply = mock_if.replies[0][0]
        self.assertIn("Boletín Vespertino", first_reply)

    def test_scheduled_message_update(self):
        msg_id = self.db.create_scheduled_message(
            message="/boletin vespertino",
            channels=[6],
            period_type="days",
            period_value=1,
            start_at="2026-08-28T20:30:00",
            enabled=1,
        )
        self.assertIsNotNone(msg_id)

        # Actualizar campos directamente
        ok = self.db.update_scheduled_message(msg_id, {
            "period_type": "hours",
            "period_value": 12,
            "channels": [6],
            "start_at": "2026-08-29T08:00:00"
        })
        self.assertTrue(ok)

        m = self.db.get_scheduled_message(msg_id)
        self.assertEqual(m["period_type"], "hours")
        self.assertEqual(m["period_value"], 12)
        self.assertEqual(m["start_at"], "2026-08-29T08:00:00")
        self.assertEqual(m["next_run_at"], "2026-08-29T08:00:00")

        self.db.delete_scheduled_message(msg_id)

    def test_estado_and_stats_channel_restriction(self):
        mock_if = MockInterface()

        # Call in general channel (ch 0) -> Should NOT reply
        estado_callback(mock_if, [], "/estado", {"is_direct": False, "channel": 0})
        self.assertEqual(len(mock_if.replies), 0)

        stats_callback(mock_if, [], "/stats", {"is_direct": False, "channel": 0})
        self.assertEqual(len(mock_if.replies), 0)

        # Call in direct message -> Should reply
        estado_callback(mock_if, [], "/estado", {"is_direct": True, "channel": 0})
        self.assertEqual(len(mock_if.replies), 1)
        self.assertIn("Bot", mock_if.replies[0][0])

        # Call in #bots channel (ch 4) -> Should reply
        stats_callback(mock_if, [], "/stats", {"is_direct": False, "channel": 4})
        self.assertGreaterEqual(len(mock_if.replies), 2)

    def test_aemet_jwt_expiry(self):
        import base64
        import json
        from Models.Aemet import Aemet

        # Crear un JWT sintético válido con expiración dentro de 20 días
        future_ts = int((datetime.now() + timedelta(days=20)).timestamp())
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps({"iss": "AEMET", "exp": future_ts}).encode()).decode().rstrip("=")
        token = f"{header}.{payload}.dummy_signature"

        aemet = Aemet()
        is_exp, days, exp_date = aemet.check_api_key_expiry(token)
        self.assertFalse(is_exp)
        self.assertIn(days, (19, 20))
        self.assertIsNotNone(exp_date)

        # Token caducado
        past_ts = int((datetime.now() - timedelta(days=5)).timestamp())
        payload_exp = base64.urlsafe_b64encode(json.dumps({"iss": "AEMET", "exp": past_ts}).encode()).decode().rstrip("=")
        token_exp = f"{header}.{payload_exp}.dummy_signature"
        is_exp_past, days_past, _ = aemet.check_api_key_expiry(token_exp)
        self.assertTrue(is_exp_past)
        self.assertLess(days_past, 0)

    def test_aemet_forecast_and_coastal_formatters(self):
        from Models.Aemet import Aemet
        aemet = Aemet()

        mock_daily = [{
            "nombre": "Chipiona",
            "prediccion": {
                "dia": [
                    {"fecha": "2026-08-29T00:00:00", "temperatura": {"minima": "21", "maxima": "30"}, "estadoCielo": [{"descripcion": "Despejado"}], "probPrecipitacion": [{"value": "0"}]},
                    {"fecha": "2026-08-30T00:00:00", "temperatura": {"minima": "20", "maxima": "29"}, "estadoCielo": [{"descripcion": "Poco nuboso"}], "probPrecipitacion": [{"value": "10"}], "viento": [{"direccion": "SO", "velocidad": "15"}], "uvMax": "8"},
                    {"fecha": "2026-08-31T00:00:00", "temperatura": {"minima": "20", "maxima": "28"}, "estadoCielo": [{"descripcion": "Despejado"}]},
                ]
            }
        }]

        # 3 días
        res_3d = aemet.format_daily_forecast(mock_daily, days=3)
        self.assertIn("Chipiona", res_3d)
        self.assertIn("Hoy 21-30°C", res_3d)
        self.assertIn("Mañana 20-29°C", res_3d)

        # Mañana detallado
        res_tom = aemet.format_tomorrow_forecast(mock_daily)
        self.assertIn("Mañana", res_tom)
        self.assertIn("20-29°C", res_tom)
        self.assertIn("UV 8", res_tom)

        # Marítimo costero
        mock_mar = [{
            "nombre": "Boletín Costero",
            "prediccion": {
                "zona": [
                    {
                        "nombre": "Aguas costeras de Cádiz",
                        "subzona": [
                            {
                                "nombre": "Del Guadalquivir al Cabo Roche",
                                "texto": "NW 4 o 5 amainando pronto a N o NW 3 o 4. Marejada disminuyendo a marejadilla. Mar de fondo del W o NW de 1 m mar adentro disminuyendo"
                            }
                        ]
                    }
                ]
            }
        }]
        res_mar = aemet.format_maritime_coastal(mock_mar)
        self.assertIn("Del Guadalquivir al Cabo Roche", res_mar)
        self.assertIn("marejadilla", res_mar.lower())

    def test_weather_and_prevision_and_marea_callbacks(self):
        from Commands.weather import weather_callback
        from Commands.prevision import prevision_callback
        from Commands.marea import marea_callback
        from Commands.help import help_callback

        mock_if = MockInterface()

        # /prevision 3 dias
        prevision_callback(mock_if, ["3", "dias"], "/prevision 3 dias", {"is_direct": True, "channel": 0})
        self.assertGreaterEqual(len(mock_if.replies), 1)

        # /marea
        mock_if.replies.clear()
        marea_callback(mock_if, [], "/marea", {"is_direct": True, "channel": 0})
        self.assertGreaterEqual(len(mock_if.replies), 1)

        # /help prevision
        mock_if.replies.clear()
        help_callback(mock_if, ["prevision"], "/help prevision", {"is_direct": True, "channel": 0})
        self.assertGreaterEqual(len(mock_if.replies), 1)
        self.assertIn("/prevision", mock_if.replies[0][0])


if __name__ == "__main__":
    unittest.main()

