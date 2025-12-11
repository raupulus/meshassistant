import env
from time import sleep
from functions import log_p
from Models.SerialInterface import SerialInterface
from create_db import ensure_database
import json

# Ruta del dispositivo serial
SERIAL_DEVICE_PATH = env.SERIAL_DEVICE_PATH

def loop():
    interface = SerialInterface(SERIAL_DEVICE_PATH)

    try:
        interface.connect()

        # Mantener el script ejecutándose
        from Models.Database import Database
        db = Database()

        while True:
            # Procesar (si hay) un trace pendiente encolado por cron (en la misma tabla traces)
            try:
                pending = db.get_next_pending_trace()
                if pending:
                    node_id = pending.get('to')
                    try:
                        # Ejecutar traceroute y capturar texto + hops hacia destino
                        result = interface.traceroute(node_id)
                        text = (result or {}).get('text', '')
                        forward = (result or {}).get('forward', []) or []
                        backward = (result or {}).get('backward', []) or []

                        # Resolver nombres del destino
                        to_row = db.get_node(node_id)
                        to_name = (to_row or {}).get('name') if to_row else None
                        to_short = (to_row or {}).get('short_name') if to_row else None

                        # Construir hasta 7 hops de ida con nombres desde BD (si existen)
                        hops = []
                        for hop in forward[:7]:
                            hid = hop.get('id')
                            hsnr = hop.get('snr')
                            hrow = db.get_node(hid) if hid else None
                            hops.append({
                                'id': hid,
                                'name': (hrow or {}).get('name') if hrow else None,
                                'name_short': (hrow or {}).get('short_name') if hrow else None,
                                'snr': hsnr,
                                'rssi': (hrow or {}).get('rssi') if hrow else None,
                            })

                        # Construir hasta 7 hops de regreso
                        return_hops = []
                        for hop in backward[:7]:
                            hid = hop.get('id')
                            hsnr = hop.get('snr')
                            hrow = db.get_node(hid) if hid else None
                            return_hops.append({
                                'id': hid,
                                'name': (hrow or {}).get('name') if hrow else None,
                                'name_short': (hrow or {}).get('short_name') if hrow else None,
                                'snr': hsnr,
                                'rssi': (hrow or {}).get('rssi') if hrow else None,
                            })

                        # Marcar trace como completado en la MISMA fila, guardando el texto en data_raw
                        db.mark_trace_done_with_route(
                            pending['id'], True,
                            text=text,
                            to_name=to_name,
                            to_name_short=to_short,
                            hops=hops,
                            return_hops=return_hops,
                        )
                    except Exception as e:
                        # En caso de fallo, guardar el error como texto plano en data_raw
                        error_txt = f"{e.__class__.__name__}: {e}"
                        db.mark_trace_done_with_route(
                            pending['id'], False,
                            text=error_txt,
                            to_name=None,
                            to_name_short=None,
                            hops=None,
                        )
            except Exception:
                # No interrumpir el loop por errores de BD
                pass

            sleep(5)

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
        # Asegurar base de datos creada (solo crea si no existe)
        ensure_database()
        loop()
    finally:
        sleep(10)

if __name__ == "__main__":
    main()
