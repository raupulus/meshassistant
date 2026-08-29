from __future__ import annotations
from datetime import datetime
from typing import List, Optional

import env
from functions import MESH_MAX_BYTES, split_messages, sanitize_text
from Models.Database import Database


class BulletinGenerator:
    """Generador de boletines periódicos para la comunidad de la malla (ámbito provincial)."""

    @staticmethod
    def build_bulletin_text(slot_name: str = "Diario") -> str:
        """Construye el texto unificado del boletín diario."""
        db = Database()
        prov_name = getattr(env, "AEMET_PROVINCE", None) or getattr(env, "LOCATION_NAME", "Cádiz") or "Cádiz"
        loc_display = "Cádiz" if str(prov_name).lower() in ("cadiz", "cádiz") else str(prov_name)

        # 1. Información Solar y Lunar
        astro_items = []
        try:
            from Models.Astro import sun_info, moon_phase
            s_info = sun_info()
            sr = s_info.get("sunrise")
            ss = s_info.get("sunset")
            if sr and ss:
                astro_items.append(f"☀️ {sr.strftime('%H:%M')}-{ss.strftime('%H:%M')}")

            m_info = moon_phase()
            p_name = m_info.get("phase_name", "")
            p_abbr = p_name.replace("Luna ", "").capitalize()
            illum = int(round(m_info.get("illumination", 0) * 100))
            if p_abbr:
                astro_items.append(f"🌙 {p_abbr} ({illum}%)")
        except Exception:
            pass

        astro_txt = " | ".join(astro_items) if astro_items else ""

        # 2. Información Meteorológica (AEMET o en caché)
        clima_txt = "🌦️ Tiempo: Despejado / Sin datos."
        try:
            w = db.aemet_weather_get_latest(province=prov_name, day="hoy")
            if not w:
                w = db.aemet_weather_get_latest(province=prov_name)
            if not w:
                w = db.aemet_weather_get_latest(day="hoy")
            if w and w.get("content"):
                raw_c = w["content"].strip()
                # Quitar prefijo redundante provincial si viene en el texto
                for prefix in ("CÁDIZ ", "CADIZ ", "Cádiz ", "Cadiz "):
                    if raw_c.startswith(prefix):
                        raw_c = raw_c[len(prefix):].strip()
                        break
                first_line = raw_c.split(".")[0] if "." in raw_c else raw_c
                first_line = sanitize_text(first_line)
                if len(first_line) > 42:
                    first_line = first_line[:39] + "…"
                clima_txt = f"🌦️ {first_line}."
        except Exception:
            pass

        # 3. Mareas (Costa)
        marea_txt = "🌊 Mareas: Sin datos."
        try:
            from Models.Tides import next_extremes, compute_tides
            t_data = db.tides_get_latest()
            extremes = []
            if t_data and t_data.get("extremes"):
                for e in t_data["extremes"]:
                    t = e.get("time")
                    try:
                        dt = datetime.fromisoformat(t) if isinstance(t, str) else t
                        extremes.append({"time": dt, "type": e.get("type"), "height": e.get("height")})
                    except Exception:
                        continue

            tz = extremes[0]["time"].tzinfo if extremes else None
            now = datetime.now(tz) if tz else datetime.now()
            upcoming = next_extremes(extremes, now=now, count=2) if extremes else []

            if not upcoming:
                # Fallback de cálculo astronómico offline
                t_comp = compute_tides(days=2, allow_network=False)
                if t_comp and t_comp.get("extremes"):
                    tz_c = t_comp["extremes"][0]["time"].tzinfo if t_comp["extremes"] else None
                    now_c = datetime.now(tz_c) if tz_c else datetime.now()
                    upcoming = next_extremes(t_comp["extremes"], now=now_c, count=2)

            if upcoming:
                etiquetas = {"high": "Plea", "low": "Baja"}
                t_parts = []
                for e in upcoming:
                    hhmm = e["time"].strftime("%H:%M")
                    et = etiquetas.get(e.get("type"), "?")
                    h = e.get("height")
                    if h is not None:
                        t_parts.append(f"{et} {hhmm} ({h:.1f}m)")
                    else:
                        t_parts.append(f"{et} {hhmm}")
                marea_txt = "🌊 Mareas: " + ", ".join(t_parts)
        except Exception:
            pass

        # 4. Alertas activas de la provincia
        avisos_txt = "⚠️ Sin avisos activos."
        try:
            with db._connect() as conn:
                cur = conn.execute(
                    "SELECT message, data_raw FROM aemet WHERE created_at >= datetime('now', '-24 hours', 'localtime') ORDER BY id DESC LIMIT 1"
                )
                row = cur.fetchone()
                if row:
                    msg_al = (row["message"] or row["data_raw"] or "").strip()
                    msg_al = sanitize_text(msg_al)
                    if msg_al:
                        first_al = msg_al.split(".")[0] if "." in msg_al else msg_al
                        if len(first_al) > 40:
                            first_al = first_al[:37] + "…"
                        avisos_txt = f"⚠️ Alerta: {first_al}."
        except Exception:
            pass

        lines = [f"📢 [Boletín {slot_name}] 📍 {loc_display}"]
        if astro_txt:
            lines.append(astro_txt)
        if clima_txt:
            lines.append(clima_txt)
        lines.append(marea_txt)
        lines.append(avisos_txt)

        return "\n".join(lines)

    @staticmethod
    def build_bulletin(slot_name: str = "Diario") -> List[str]:
        """Construye las partes del boletín diario (<= 200 bytes por mensaje)."""
        full_text = BulletinGenerator.build_bulletin_text(slot_name=slot_name)
        parts = split_messages(full_text, max_bytes=MESH_MAX_BYTES, max_parts=2)
        return parts if parts else [full_text]
