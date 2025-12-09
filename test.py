
#!/usr/bin/env python3
"""
Ejemplo simple para recibir mensajes de Meshtastic por UART
y mostrarlos en consola identificando origen (grupo/directo)
"""

from meshtastic import serial_interface
from pubsub import pub


def on_receive(packet, interface):
    """
    Callback que se ejecuta cuando se recibe un mensaje
    """
    try:
        # Verificar si el paquete contiene un mensaje de texto
        if 'decoded' in packet and 'text' in packet['decoded']:
            mensaje = packet['decoded']['text']

            # Obtener información del remitente
            from_id = packet.get('fromId', 'Desconocido')
            from_num = packet.get('from', 'N/A')
            to_id = packet.get('toId', 'Desconocido')
            to_num = packet.get('to', 'N/A')

            # Determinar si es mensaje directo o de grupo
            # En Meshtastic, si el destino es "^all" o un canal, es mensaje de grupo
            if to_id == '^all' or to_num == 0xFFFFFFFF:
                tipo = "📢 GRUPO"
            else:
                tipo = "💬 DIRECTO"

            # Obtener canal si existe

            print('antes de get channel')
            canal = packet.get('channel', 0)
            print('después de get channel')

            # Imprimir el mensaje formateado
            print(f"\n{'=' * 60}")
            print(f"{tipo}")
            print(f"De: {from_id} ({from_num})")
            print(f"Para: {to_id} ({to_num})")
            print(f"Canal: {canal}")
            print(f"Mensaje: {mensaje}")
            print(f"{'=' * 60}\n")

    except Exception as e:
        print(f"Error procesando paquete: {e}")


def main():
    """
    Función principal
    """
    print("🚀 Iniciando receptor de mensajes Meshtastic por UART...")
    print("Presiona Ctrl+C para salir\n")

    try:
        # Conectar al dispositivo por puerto serial
        interface = serial_interface.SerialInterface(devPath='/dev/cu.usbserial-212110')

        print(f"✅ Conectado al dispositivo Meshtastic")
        print(f"Esperando mensajes...\n")

        # Suscribirse al topic de mensajes recibidos
        pub.subscribe(on_receive, "meshtastic.receive")

        # Mantener el script ejecutándose
        while True:
            pass

    except KeyboardInterrupt:
        print("\n\n👋 Cerrando conexión...")
        interface.close()
        print("✅ Desconectado correctamente")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nAsegúrate de que:")
        print("  - El dispositivo Meshtastic está conectado por USB/UART")
        print("  - Tienes permisos para acceder al puerto serial")
        print(
            "  - La librería meshtastic está instalada: pip install meshtastic")


if __name__ == "__main__":
    main()