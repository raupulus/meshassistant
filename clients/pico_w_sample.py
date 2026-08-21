"""Cliente de ejemplo agnóstico para Raspberry Pi Pico W / MicroPython / Python 3.

Demuestra cómo conectar vía WiFi / WebSocket a Meshassistant Gateway (puerto 8680),
solicitar el snapshot inicial de la red y procesar eventos en tiempo real.
"""

from __future__ import annotations

import json
import time
import sys

# Configuración de conexión
GATEWAY_HOST = "192.168.1.50"  # Cambiar por la IP de la Raspberry Pi Zero 2W
GATEWAY_PORT = 8680
WS_URL = f"ws://{GATEWAY_HOST}:{GATEWAY_PORT}"


def process_event(event_obj: dict) -> None:
    """Parsea y procesa los eventos entrantes del WebSocket."""
    event_name = event_obj.get("event")
    data = event_obj.get("data", {})
    ts = event_obj.get("ts", "")

    if event_name == "welcome":
        print(f"[*] Conectado a Gateway. Servidor: {data.get('server')} v{data.get('version')}")

    elif event_name == "message_rx":
        sender = data.get("from_short_name") or data.get("from_name") or data.get("from")
        channel = data.get("channel", 0)
        text = data.get("text", "")
        snr = data.get("snr")
        print(f"[{ts}] [CH {channel}] <{sender}> (SNR: {snr}dB): {text}")

    elif event_name == "node_discovered" or event_name == "node_updated":
        name = data.get("name") or data.get("short_name") or data.get("id")
        print(f"[*] Nodo actualizado: {name} ({data.get('id')}) | SNR: {data.get('snr')}")

    elif event_name == "device_telemetry":
        node_id = data.get("id")
        bat = data.get("battery")
        volt = data.get("voltage")
        print(f"[Telemetría] Nodo {node_id} -> Batería: {bat}% ({volt}V)")

    elif event_name == "channel_metrics":
        ch_util = data.get("channel_util")
        air_tx = data.get("air_util_tx")
        print(f"[Canal LoRa] Ocupación espectro: {ch_util}% | AirUtilTx: {air_tx}%")

    elif event_name == "trace_completed":
        to_name = data.get("to_name") or data.get("to")
        hops_fwd = data.get("hops_forward", [])
        print(f"[Traceroute OK] Destino: {to_name} | Saltos de ida: {len(hops_fwd)}")
        for i, h in enumerate(hops_fwd, start=1):
            h_name = h.get("name") or h.get("id")
            print(f"   Salto {i}: {h_name} (SNR: {h.get('snr')} dB)")

    elif event_name == "system_status":
        uart = "OK" if data.get("uart_connected") else "DESCONECTADO"
        uptime = data.get("bot_uptime", 0)
        print(f"[Heartbeat] UART: {uart} | Uptime: {uptime}s")

    elif event_name == "aemet_alert":
        print(f"[ALERTA AEMET] {data.get('level').upper()} en {data.get('province')}: {data.get('message')}")

    else:
        print(f"[Evento: {event_name}] {data}")


# ==========================================
# Modo de ejecución en Python 3 (Desktop/CLI)
# ==========================================
async def run_desktop_client(url: str = WS_URL):
    try:
        import websockets
    except ImportError:
        print("Instala websockets con: pip install websockets")
        return

    print(f"Conectando a {url}...")
    async with websockets.connect(url) as ws:
        # 1. Pedir snapshot inicial
        snapshot_req = {
            "action": "get_snapshot",
            "req_id": "init_001",
            "params": {"include": ["nodes", "routers", "recent_messages", "system_status"]},
        }
        await ws.send(json.dumps(snapshot_req))

        # 2. Bucle de recepción
        async for message in ws:
            try:
                obj = json.loads(message)
                if obj.get("type") == "response":
                    print("[*] Snapshot recibido:", json.dumps(obj.get("data"), indent=2))
                else:
                    process_event(obj)
            except Exception as e:
                print("Error procesando mensaje:", e)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        WS_URL = sys.argv[1]

    try:
        import asyncio
        asyncio.run(run_desktop_client(WS_URL))
    except KeyboardInterrupt:
        print("\nCliente detenido.")
