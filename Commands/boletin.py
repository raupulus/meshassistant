from __future__ import annotations
from datetime import datetime
from time import sleep
from Models.Bulletin import BulletinGenerator


def boletin_callback(interface, args, msg, metadata):
    """/boletin — Resumen meteorológico, astronómico y de mareas (matinal/vespertino).

    Uso: /boletin [matinal|vespertino]
    """
    try:
        slot_name = None
        if args:
            arg_lower = str(args[0]).lower()
            if "mat" in arg_lower:
                slot_name = "Matinal"
            elif "vesp" in arg_lower or "tard" in arg_lower or "noch" in arg_lower:
                slot_name = "Vespertino"

        if not slot_name:
            slot_name = "Matinal" if datetime.now().hour < 14 else "Vespertino"

        parts = BulletinGenerator.build_bulletin(slot_name=slot_name)
        for idx, part in enumerate(parts):
            interface.reply_to_message(part, metadata)
            if idx < len(parts) - 1:
                sleep(2.5)
    except Exception as e:
        interface.reply_to_message(f"Error generando boletín: {e}", metadata)
