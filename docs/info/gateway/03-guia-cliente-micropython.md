# 03 · Guía de Cliente MicroPython (Raspberry Pi Pico W)

Esta guía explica cómo conectar una **Raspberry Pi Pico W / Pico 2 W** ejecutando **MicroPython** al servidor WebSocket de `meshassistant` (puerto `8680`) para recibir mensajes y telemetría en tiempo real y mostrarlos en una pantalla (LCD ST7789, ILI9341 u OLED SSD1306).

---

## 1. Requisitos en MicroPython

1. **Firmware MicroPython con soporte WiFi** (v1.20 o superior).
2. Librería cliente de WebSockets ligera para MicroPython (p. ej. `micropython-ws` o socket raw TCP con framing WebSocket).

---

## 2. Ejemplo Completo en MicroPython

```python
import network
import time
import ujson
import usocket

# 1. Conexión WiFi
SSID = "MiRedWiFi"
PASSWORD = "PasswordSeguro"
GATEWAY_IP = "192.168.1.50"  # IP de la Raspberry Pi Zero 2 W
GATEWAY_PORT = 8680

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Conectando a WiFi...")
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("WiFi Conectado:", wlan.ifconfig())

connect_wifi()

# 2. Cliente de eventos WebSocket
# Usando una librería WebSocket ligera de MicroPython (o sockets)
# Para código agnóstico completo, ver: clients/pico_w_sample.py
```

---

## 3. Optimización de Memoria en la Pico W

1. **Lectura Línea a Línea:** Los payloads JSON del Gateway tienen claves directas y planas para que `ujson.loads()` consuma menos de 2 KB de RAM durante el parseo.
2. **Buffer de Pantalla:** Limita el refresco de pantalla a eventos clave (`message_rx`, `trace_completed`, `router_status`) y descarta campos no utilizados inmediatamente.
3. **Reconexión Automática:** En caso de corte de WiFi o reinicio de la Raspberry Pi, mantén un bucle de reintento con *backoff* exponencial (2s, 4s, 8s, máx 30s) para volver a conectar sin desbordar el stack.
