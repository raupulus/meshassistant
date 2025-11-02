import env
from time import sleep
from functions import log_p, get_commands_dict
from Models.SerialInterface import SerialInterface

# Ruta del dispositivo serial
SERIAL_DEVICE_PATH = env.SERIAL_DEVICE_PATH

def loop():
    interface = SerialInterface(SERIAL_DEVICE_PATH)

    try:
        interface.connect()

        # Mantener el script ejecutándose
        while True:
            pass

    except KeyboardInterrupt:
        print("\n\n👋 Cerrando conexión...")
        if interface:
            interface.disconnect()
        print("Desconectado correctamente")

        exit(0)

    except Exception as e:
        print(f"Error: {e}")
        print("\nAsegúrate de que:")
        print("  - El dispositivo Meshtastic está conectado por USB/UART")
        print("  - Tienes permisos para acceder al puerto serial")
        print("  - La librería meshtastic está instalada: pip install meshtastic")
        if interface:
            sleep(5)
            interface.disconnect()


def main():
    log_p("Iniciando receptor de mensajes Meshtastic por UART...")
    log_p("Presiona Ctrl+C para salir\n")

    try:
        loop()
    finally:
        sleep(10)

if __name__ == "__main__":
    main()
