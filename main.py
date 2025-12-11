import env
from time import sleep
from functions import log_p
from Models.SerialInterface import SerialInterface
from create_db import ensure_database
import json
from functions import sanitize_text

# Ruta del dispositivo serial
SERIAL_DEVICE_PATH = env.SERIAL_DEVICE_PATH

def loop():
    interface = SerialInterface(SERIAL_DEVICE_PATH)

    try:
        interface.connect()

        # Mantener el script ejecutándose
        from Models.Database import Database
        from Models.Aemet import Aemet
        db = Database()
        aemet = Aemet()

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

            # Publicación de alertas AEMET mínima (si hay API key y dentro de ventana horaria)
            try:
                if getattr(__import__('env'), 'AEMET_API_KEY', None):
                    # Respetar ventana horaria
                    now_hour = __import__('datetime').datetime.now().hour
                    if aemet.is_within_hour_window(now_hour):
                        # Comprobar siguiente alerta sin publicar
                        alert = db.aemet_get_next_unpublished()
                        if alert:
                            # Comprobar período por canal
                            period_min = aemet.period_to_minutes(getattr(aemet, 'period', 'Hour'))
                            publish_channels = []
                            for ch in (aemet.channels or []):
                                last = db.get_task_last_run(f'aemet_publish_ch_{ch}')
                                if not last:
                                    publish_channels.append(ch)
                                else:
                                    try:
                                        last_dt = __import__('datetime').datetime.fromisoformat(last)
                                        if __import__('datetime').datetime.now() - last_dt >= __import__('datetime').timedelta(minutes=period_min):
                                            publish_channels.append(ch)
                                    except Exception:
                                        publish_channels.append(ch)

                            if publish_channels:
                                # Preparar mensajes respetando límite de 200 caracteres y encabezados
                                # Usar mensaje preparado para publicación si existe; fallback a data_raw
                                raw_msg = (alert.get('message') or alert.get('data_raw') or '').strip()
                                # Normalizar y sanear texto base (evitar artefactos de XML)
                                base_text = sanitize_text(raw_msg)

                                def build_aemet_messages(text: str) -> list[str]:
                                    # Mensajería Meshtastic: máx 200 caracteres por mensaje
                                    MAX_LEN = 200
                                    hdr_single = 'AEMET:'
                                    hdr_part1 = 'AEMET 1/2:'
                                    hdr_part2 = 'AEMET 2/2:'
                                    tail_link = ' Ver: https://www.aemet.es'

                                    # Caso 1: cabe en un único mensaje
                                    body_cap_single = MAX_LEN - (len(hdr_single) + 1)  # espacio tras cabecera
                                    if len(text) <= body_cap_single:
                                        return [f"{hdr_single} {text}"]

                                    # Caso 2: dividir en 2 partes (máximo) y truncar si excede
                                    body_cap_p1 = MAX_LEN - (len(hdr_part1) + 1)
                                    body_cap_p2 = MAX_LEN - (len(hdr_part2) + 1 + len(tail_link))
                                    if body_cap_p2 < 0:
                                        # Seguridad: si por alguna razón el tail excede, no añadimos enlace
                                        body_cap_p2 = MAX_LEN - (len(hdr_part2) + 1)
                                        _tail = ''
                                    else:
                                        _tail = tail_link

                                    # Particionar texto
                                    part1 = text[:body_cap_p1]
                                    remaining = text[len(part1):]
                                    part2 = remaining[:body_cap_p2]

                                    msg1 = f"{hdr_part1} {part1}"
                                    msg2 = f"{hdr_part2} {part2}{_tail}"

                                    # Garantizar límites por si acaso
                                    msg1 = msg1[:MAX_LEN]
                                    msg2 = msg2[:MAX_LEN]
                                    return [msg1, msg2]

                                messages = build_aemet_messages(base_text)

                                sent_any = False
                                for ch in publish_channels:
                                    # Enviar uno o dos mensajes (si hay 2, con 5s entre ellos) ignorando cooldown intra-alerta
                                    part_ok = False
                                    for idx, msg in enumerate(messages):
                                        ok = interface.send(msg, dest='^all', channel=ch)
                                        if ok:
                                            part_ok = True
                                        # Esperar 5s entre partes si hay más de una
                                        if len(messages) > 1 and idx == 0:
                                            sleep(5)
                                    if part_ok:
                                        sent_any = True
                                        # Marcar periodo por canal tras completar el envío (1 o 2 partes)
                                        db.set_task_run(f'aemet_publish_ch_{ch}')

                                if sent_any:
                                    db.aemet_mark_published(alert['id'])
            except Exception:
                # No romper el loop por AEMET
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
