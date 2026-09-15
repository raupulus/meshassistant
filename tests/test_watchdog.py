import time
import unittest
from unittest.mock import MagicMock, patch

import env
from Models.SerialInterface import SerialInterface


class TestSerialWatchdog(unittest.TestCase):
    def setUp(self):
        # Crear instancia de SerialInterface con puerto simulado
        self.si = SerialInterface("/dev/mock_serial")
        self.si.interface = MagicMock()
        # Mock de _rxThread vivo
        self.mock_thread = MagicMock()
        self.mock_thread.is_alive.return_value = True
        self.si.interface._rxThread = self.mock_thread

    def test_initial_state_and_touch_rx(self):
        """Verifica marcas temporales y reseteo tras touch_rx."""
        self.assertFalse(self.si._needs_reconnect)
        self.assertEqual(self.si.consecutive_trace_timeouts, 0)
        old_ts = self.si.last_rx_timestamp

        time.sleep(0.01)
        self.si._touch_rx()
        self.assertGreater(self.si.last_rx_timestamp, old_ts)

    def test_record_trace_metrics(self):
        """Verifica contadores de éxito y timeout en trazas."""
        self.assertEqual(self.si.consecutive_trace_timeouts, 0)
        self.si.record_trace_timeout()
        self.si.record_trace_timeout()
        self.assertEqual(self.si.consecutive_trace_timeouts, 2)

        self.si.record_trace_success()
        self.assertEqual(self.si.consecutive_trace_timeouts, 0)

    def test_watchdog_healthy(self):
        """Si hay actividad reciente y el hilo está vivo, el watchdog debe dar True."""
        self.si.last_watchdog_check = 0  # forzar chequeo inmediato
        self.si.last_rx_timestamp = time.time()
        result = self.si.check_watchdog()
        self.assertTrue(result)
        self.assertFalse(self.si._needs_reconnect)

    def test_watchdog_dead_rx_thread(self):
        """Si el hilo lector ha muerto, debe solicitar reconexión inmediata."""
        self.mock_thread.is_alive.return_value = False
        self.si.last_watchdog_check = 0

        with patch("Models.SerialInterface.log_p") as mock_log:
            result = self.si.check_watchdog()
            self.assertFalse(result)
            self.assertTrue(self.si._needs_reconnect)
            mock_log.assert_called()

    def test_watchdog_rx_timeout(self):
        """Si transcurre más tiempo que el umbral configurado, debe solicitar reconexión."""
        self.si.last_watchdog_check = 0
        # Simular inactividad de 25 minutos
        self.si.last_rx_timestamp = time.time() - (25 * 60)

        with patch.object(env, "SERIAL_WATCHDOG_TIMEOUT_MINUTES", 20, create=True):
            with patch("Models.SerialInterface.log_p") as mock_log:
                result = self.si.check_watchdog()
                self.assertFalse(result)
                self.assertTrue(self.si._needs_reconnect)
                mock_log.assert_called()

    def test_watchdog_consecutive_trace_timeouts(self):
        """Si fallan N traces consecutivos y hay silencio prolongado, solicita reconexión."""
        self.si.last_watchdog_check = 0
        self.si.consecutive_trace_timeouts = 5
        # 6 minutos de silencio
        self.si.last_rx_timestamp = time.time() - 360

        with patch.object(env, "SERIAL_WATCHDOG_MAX_TRACE_TIMEOUTS", 5, create=True):
            with patch("Models.SerialInterface.log_p") as mock_log:
                result = self.si.check_watchdog()
                self.assertFalse(result)
                self.assertTrue(self.si._needs_reconnect)
                mock_log.assert_called()

    def test_watchdog_disabled(self):
        """Si el watchdog está deshabilitado en env, no debe solicitar reconexión."""
        self.si.last_watchdog_check = 0
        self.si.last_rx_timestamp = time.time() - (60 * 60)  # 1 hora de silencio

        with patch.object(env, "SERIAL_WATCHDOG_ENABLED", False, create=True):
            result = self.si.check_watchdog()
            self.assertTrue(result)
            self.assertFalse(self.si._needs_reconnect)


if __name__ == "__main__":
    unittest.main()
