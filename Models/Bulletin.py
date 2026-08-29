from __future__ import annotations
from datetime import datetime
from typing import List, Optional

import env
from functions import MESH_MAX_BYTES, split_messages, sanitize_text
from Models.Database import Database


class BulletinGenerator:
    """Generador de boletines periódicos para la comunidad de la malla (ámbito provincial)."""

    @staticmethod
    def build_bulletin(slot_name: str = "Diario") -> List[str]:
        """Construye las partes del boletín diario (máx 2 partes de <= 200 bytes)."""
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
                astro_items.append(f"☀️ Sol {sr.strftime('%H:%M')}-{ss.strftime('%H:%M')}")

            m_info = moon_phase()
            p_name = m_info.get("phase_name", "")
            illum = int(round(m_info.get("illumination", 0) * 100))
            if p_name:
                astro_items.append(f"🌙 {p_name} ({illum}%)")
        except Exception:
            pass

        astro_txt = " | ".join(astro_items) if astro_items else ""

        # 2. Información Meteorológica (AEMET o en caché)
        clima_txt = "🌦️ Tiempo: Despejado / Sin datos."
        try:
            w = db.aemet_weather_get_latest()
            if w and w.get("content"):
                raw_c = w["content"].strip()
                # Extraer resumen conciso (primera frase o hasta 85 caracteres)
                first_line = raw_c.split(".")[0] if "." in raw_c else raw_c
                first_line = sanitize_text(first_line)
                if len(first_line) > 85:
                    first_line = first_line[:82] + "…"
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
            upcoming = next_extremes(extremes, now=now, count=3) if extremes else []

            if not upcoming:
                # Fallback de cálculo astronómico offline
                t_comp = compute_tides(days=2, allow_network=False)
                if t_comp and t_comp.get("extremes"):
                    tz_c = t_comp["extremes"][0]["time"].tzinfo if t_comp["extremes"] else None
                    now_c = datetime.now(tz_c) if tz_c else datetime.now()
                    upcoming = next_extremes(t_comp["extremes"], now=now_c, count=3)

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
        avisos_txt = "⚠️ Avisos: Sin alertas activas."
        try:
            with db._connect() as conn:
                # Comprobar alertas de las últimas 24h
                cur = conn.execute(
                    "SELECT message, data_raw FROM aemet WHERE created_at >= datetime('now', '-24 hours', 'localtime') ORDER BY id DESC LIMIT 1"
                )
                row = cur.fetchone()
                if row:
                    msg_al = (row["message"] or row["data_raw"] or "").strip()
                    msg_al = sanitize_text(msg_al)
                    if msg_al:
                        first_al = msg_al.split(".")[0] if "." in msg_al else msg_al
                        if len(first_al) > 60:
                            first_al = first_al[:57] + "…"
                        avisos_txt = f"⚠️ Alerta: {first_al}."
        except Exception:
            pass

        # Construir Parte 1: Cabecera + Astro (Sol & Luna) + Clima
        p1_lines = [f"📢 [Boletín {slot_name}] 📍 {loc_display}"]
        if astro_txt:
            p1_lines.append(astro_txt)
        if clima_txt:
            p1_lines.append(clima_txt)
        part1 = "\n".join(p1_lines)

        # Construir Parte 2: Mareas + Alertas
        p2_lines = [marea_txt, avisos_txt]
        part2 = "\n".join(p2_lines)

        messages = []
        # Asegurar ajuste estricto a MESH_MAX_BYTES por mensaje
        for p in [part1, part2]:
            sub_chunks = split_messages(p, max_bytes=MESH_MAX_BYTES, max_parts=1)
            if sub_chunks:
                messages.append(sub_chunks[0])

        return messages
