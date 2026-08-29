import time
from datetime import datetime

# Marca temporal de arranque del proceso. Se fija una sola vez al importar este
# módulo (ocurre al inicio del daemon), así /uptime mide el tiempo real encendido
# con independencia de reconexiones del puerto serie.
STARTED_AT = datetime.now()

# Límite de bytes por mensaje en la malla Meshtastic.
MESH_MAX_BYTES = 200
# Máximo de mensajes que puede emitir la respuesta de un comando básico.
MESH_MAX_PARTS = 3


def format_uptime(since: datetime = None) -> str:
    """Devuelve el tiempo transcurrido desde `since` (por defecto STARTED_AT)
    en formato breve español: '3d 4h 12m' (omite las unidades a cero por la
    izquierda). Si es menos de un minuto, devuelve 'menos de 1m'.
    """
    ref = since or STARTED_AT
    delta = datetime.now() - ref
    total = int(delta.total_seconds())
    if total < 0:
        total = 0

    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return ' '.join(parts) if (days or hours or minutes) else 'menos de 1m'


def split_messages(text, max_bytes: int = MESH_MAX_BYTES, max_parts: int = MESH_MAX_PARTS):
    """Trocea un texto en como mucho `max_parts` mensajes de `max_bytes` bytes UTF-8.

    Intenta cortar en un límite de palabra para no partir términos. Si el texto
    excede la capacidad total, el último mensaje termina en '…'.
    """
    text = (text or '').strip()
    if not text:
        return []

    messages = []
    remaining = text
    for i in range(max_parts):
        if not remaining:
            break
        last = (i == max_parts - 1)

        if len(remaining.encode('utf-8')) <= max_bytes:
            messages.append(remaining)
            remaining = ''
            break

        # Reservar 3 bytes para el indicador de truncado '…' en el último tramo
        cap_bytes = max_bytes - 3 if last else max_bytes
        
        cut_chars = 0
        current_bytes = 0
        for char in remaining:
            char_bytes = len(char.encode('utf-8'))
            if current_bytes + char_bytes > cap_bytes:
                break
            current_bytes += char_bytes
            cut_chars += 1
            
        cut = remaining[:cut_chars]
        
        # Cortar en el último espacio para no partir palabras
        sp = cut.rfind(' ')
        if sp > int(cut_chars * 0.6):
            cut = cut[:sp]
        cut = cut.rstrip()

        if last:
            messages.append((cut + '…').strip())
            remaining = ''
        else:
            messages.append(cut)
            remaining = remaining[len(cut):].lstrip()

    return messages


def reply_long(interface, metadata, text, *, max_parts: int = MESH_MAX_PARTS):
    """Responde troceando el texto en hasta `max_parts` mensajes de la malla.

    Reutiliza split_messages y respeta el límite de ~200 bytes de Meshtastic,
    esperando 1 s entre partes para no saturar la radio.
    """
    from time import sleep

    parts = split_messages(text, max_bytes=MESH_MAX_BYTES, max_parts=max_parts)
    if not parts:
        parts = [text]
    for idx, part in enumerate(parts):
        interface.reply_to_message(part, metadata)
        if idx < len(parts) - 1:
            sleep(2.5)


def log_p(message: str, *, level: str = "INFO"):
    """Log condicionado por env.DEBUG.

    Solo imprime si env.DEBUG es True. Añade marca temporal y nivel.
    """
    try:
        import env  # se carga configuración del proyecto
        debug = getattr(env, 'DEBUG', False)
    except Exception:
        debug = False

    if not debug:
        return

    try:
        from datetime import datetime
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        ts = ''

    lvl = (level or 'INFO').upper()
    print(f"[{ts}] [{lvl}] {message}")

def search_command (msg):
    """
    Devuelve el comando y los argumentos si los tuviera.
    """
    # Verificar que el mensaje no esté vacío
    if not msg or len(msg) < 2:
        return None, []

    # Verificar que comience por / o !
    if not msg.startswith('/') and not msg.startswith('!'):
        return None, []

    # Partir en trozos al llegar a espacio
    parts = msg.split()

    # Quedarnos con el primero y quitar el caracter / o !
    comando = parts[0][1:].lower()

    from data import commands_dict

    # Buscar la primera palabra de la cadena en diccionario "command_dict"
    if comando not in commands_dict:
        return None, []

    # Devolver comando y argumentos
    return comando, parts[1:]


def sanitize_text(text: str) -> str:
    """Normaliza y limpia texto para envío/almacenamiento.

    - Convierte a forma Unicode NFKC.
    - Desescapa entidades HTML.
    - Sustituye NBSP y separadores no estándar por espacios.
    - Elimina caracteres de control no imprimibles.
    - Colapsa espacios en blanco múltiples.
    - Recorta extremos.
    """
    if text is None:
        return ''
    try:
        import unicodedata
        import html

        # Desescape HTML & normalización unicode
        t = html.unescape(str(text))
        t = unicodedata.normalize('NFKC', t)

        # Sustituir espacios no estándar
        t = t.replace('\u00A0', ' ').replace('\u2007', ' ').replace('\u202F', ' ')

        # Eliminar caracteres de control excepto \n y \t (luego colapsamos)
        t = ''.join(ch for ch in t if (ch >= ' ' or ch in ('\n', '\t')))

        # Sustituir saltos por espacios y colapsar
        t = ' '.join(t.replace('\r', ' ').replace('\n', ' ').split())

        return t.strip()
    except Exception:
        try:
            return ' '.join(str(text).split()).strip()
        except Exception:
            return ''


def get_system_telemetry() -> dict:
    """Recopila telemetría de hardware de la Raspberry Pi y del bot (CPU temp, carga, RAM, disco, uptime)."""
    import os
    import shutil

    # 1. CPU Temp
    cpu_temp = None
    try:
        thermal_path = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(thermal_path):
            with open(thermal_path, "r") as f:
                cpu_temp = round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        cpu_temp = None

    # 2. Carga CPU
    load_1m, load_5m = 0.0, 0.0
    try:
        if hasattr(os, "getloadavg"):
            l1, l5, _ = os.getloadavg()
            load_1m, load_5m = round(l1, 2), round(l5, 2)
    except Exception:
        pass

    # 3. Memoria RAM
    ram_total_mb, ram_used_mb, ram_free_mb, ram_pct = 0, 0, 0, 0.0
    try:
        meminfo_path = "/proc/meminfo"
        if os.path.exists(meminfo_path):
            mem = {}
            with open(meminfo_path, "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        k = parts[0].strip()
                        v = parts[1].strip().split()[0]
                        mem[k] = int(v)
            total_kb = mem.get("MemTotal", 0)
            avail_kb = mem.get("MemAvailable", mem.get("MemFree", 0))
            used_kb = max(0, total_kb - avail_kb)
            ram_total_mb = int(total_kb / 1024)
            ram_used_mb = int(used_kb / 1024)
            ram_free_mb = int(avail_kb / 1024)
            if ram_total_mb > 0:
                ram_pct = round((ram_used_mb / ram_total_mb) * 100, 1)
    except Exception:
        pass

    # 4. Espacio en disco
    disk_total_gb, disk_free_gb, disk_pct = 0.0, 0.0, 0.0
    try:
        usage = shutil.disk_usage("/")
        disk_total_gb = round(usage.total / (1024 ** 3), 1)
        disk_used_gb = round(usage.used / (1024 ** 3), 1)
        disk_free_gb = round(usage.free / (1024 ** 3), 1)
        if disk_total_gb > 0:
            disk_pct = round((disk_used_gb / disk_total_gb) * 100, 1)
    except Exception:
        pass

    # 5. Uptime del bot y del sistema
    bot_uptime_sec = int(time.time() - STARTED_AT.timestamp())
    bot_uptime = format_uptime(STARTED_AT)
    sys_uptime_sec = bot_uptime_sec
    sys_uptime_str = None
    try:
        uptime_path = "/proc/uptime"
        if os.path.exists(uptime_path):
            with open(uptime_path, "r") as f:
                sec = float(f.read().split()[0])
                sys_uptime_sec = int(sec)
                days, rem = divmod(int(sec), 86400)
                hours, rem = divmod(rem, 3600)
                mins = rem // 60
                u_parts = []
                if days:
                    u_parts.append(f"{days}d")
                if hours or days:
                    u_parts.append(f"{hours}h")
                u_parts.append(f"{mins}m")
                sys_uptime_str = " ".join(u_parts)
    except Exception:
        pass

    return {
        "cpu_temp": cpu_temp,
        "load_1m": load_1m,
        "load_5m": load_5m,
        "ram_total_mb": ram_total_mb,
        "ram_used_mb": ram_used_mb,
        "ram_free_mb": ram_free_mb,
        "ram_pct": ram_pct,
        "ram_percent": ram_pct,
        "disk_total_gb": disk_total_gb,
        "disk_free_gb": disk_free_gb,
        "disk_pct": disk_pct,
        "bot_uptime": bot_uptime,
        "bot_uptime_human": bot_uptime,
        "bot_uptime_seconds": bot_uptime_sec,
        "sys_uptime": sys_uptime_str or bot_uptime,
        "system_uptime_human": sys_uptime_str or bot_uptime,
        "system_uptime_seconds": sys_uptime_sec,
    }