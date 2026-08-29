from __future__ import annotations
from datetime import datetime
from functions import reply_long
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

        full_text = BulletinGenerator.build_bulletin_text(slot_name=slot_name)
        reply_long(interface, metadata, full_text, max_parts=2)
    except Exception as e:
        interface.reply_to_message(f"Error generando boletín: {e}", metadata)
