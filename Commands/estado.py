from functions import get_system_telemetry, reply_long
import env

def estado_callback(interface, args, msg, metadata):
    """/estado (/salud, /bot) — Telemetría y estado de salud de la Raspberry Pi y el bot.

    Restricción: Solo responde por mensaje directo (DM) o en el canal "bots".
    """
    metadata = metadata or {}
    is_direct = metadata.get("is_direct", False)
    channel = metadata.get("channel", 0)

    # Restricción: solo en privado o canal 'bots' (canal 4 por defecto)
    from data import channels
    ch_info = channels.get(channel, {})
    ch_name = (ch_info.get("name") or "").lower()
    
    if not is_direct and ch_name != "bots" and channel != 4:
        return

    try:
        t = get_system_telemetry()
        base_short = getattr(env, 'MESH_GATEWAY_SHORT_NAME', 'RAU0') or 'RAU0'
        
        partes = [f"🖥️ Bot ({base_short}):"]
        
        if t.get('cpu_temp') is not None:
            partes.append(f"🌡️ {t['cpu_temp']}°C")
            
        partes.append(f"⚡ Load {t.get('load_1m', 0.0)}")
        
        if t.get('ram_total_mb'):
            partes.append(f"🧠 RAM {t['ram_used_mb']}/{t['ram_total_mb']}MB ({t['ram_pct']}%)")
            
        if t.get('disk_free_gb'):
            partes.append(f"💾 {t['disk_free_gb']}GB libre")
            
        partes.append(f"⏱️ Up {t.get('bot_uptime')}")
        
        uart_ok = getattr(interface, 'interface', None) is not None or getattr(interface, 'serial_if', None) is not None
        partes.append(f"📻 UART: {'OK' if uart_ok else 'ERR'}")
        
        response = " | ".join(partes)
    except Exception as e:
        response = f"Error obteniendo telemetría: {e}"

    reply_long(interface, metadata, response)
