from __future__ import annotations
from datetime import datetime
from typing import List, Optional

import env
from functions import MESH_MAX_BYTES, split_messages, sanitize_text
from Models.Database import Database


class BulletinGenerator:
    """Generador de boletines periódicos para la comunidad de la malla (ámbito provincial)."""

    @staticmethod
    def _format_weather_text(raw_narrative: str, max_bytes: int) -> str:
        """Formatea y recorta la predicción del tiempo por palabras para ajustarse exactamente al presupuesto."""
        raw = raw_narrative.strip()
        if not raw:
            return "Despejado / Sin datos."
        if len(raw.encode("utf-8")) <= max_bytes:
            return raw

        budget = max_bytes - len("…".encode("utf-8"))
        if budget <= 0:
            return ""

        curr = 0
        cut_idx = 0
        for i, ch in enumerate(raw):
            cb = len(ch.encode("utf-8"))
            if curr + cb > budget:
                break
            curr += cb
            cut_idx = i + 1

        cand = raw[:cut_idx]

        # Si contiene un punto completo razonablemente cerca del final del presupuesto, cortar ahí
        last_dot = cand.rfind(". ")
        if last_dot > int(budget * 0.7):
            return cand[:last_dot + 1]
        elif cand.endswith("."):
            return cand

        sp = cand.rfind(" ")
        if sp > int(len(cand) * 0.4):
            cand = cand[:sp]

        cand = cand.rstrip(" ,;:-")
        if cand.endswith("."):
            return cand
        return cand + "…"

    @staticmethod
    def build_bulletin(slot_name: str = "Diario") -> List[str]:
        """Construye las partes del boletín diario (<= 200 bytes por mensaje).

        - Parte 1: Resumen principal (cabecera sin '📍 Cádiz' por defecto, sol/luna, predicción
          ampliada del tiempo aprovechando el espacio, mareas sin prefijo redundante y estado
          de avisos). Con '0 Alertas', el boletín cabe íntegro en un único mensaje.
        - Parte 2 (solo si existen avisos activos): Detalle completo de las alertas AEMET.
        """
        db = Database()
        prov_name = getattr(env, "AEMET_PROVINCE", None) or getattr(env, "LOCATION_NAME", "Cádiz") or "Cádiz"
        is_default_cadiz = str(prov_name).strip().lower() in ("cadiz", "cádiz")

        # 1. Cabecera (omitir '📍 Cádiz' por defecto ya que se sobreentiende)
        if is_default_cadiz:
            header_txt = f"📢 [Boletín {slot_name}]"
        else:
            header_txt = f"📢 [Boletín {slot_name}] 📍 {prov_name}"

        # 2. Información Solar y Lunar
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

        # 3. Mareas (Costa) - Sin prefijo de texto 'Mareas:', solo el icono 🌊
        marea_txt = "🌊 Sin datos."
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
                marea_txt = "🌊 " + ", ".join(t_parts)
        except Exception:
            pass

        # 4. Alertas activas de la provincia
        alert_rows = []
        try:
            with db._connect() as conn:
                cur = conn.execute(
                    "SELECT message, data_raw FROM aemet WHERE created_at >= datetime('now', '-24 hours', 'localtime') ORDER BY id DESC LIMIT 2"
                )
                alert_rows = [dict(r) for r in cur.fetchall()]
        except Exception:
            alert_rows = []

        alert_texts = []
        for r in alert_rows:
            msg_al = (r.get("message") or r.get("data_raw") or "").strip()
            msg_al = sanitize_text(msg_al)
            if msg_al:
                alert_texts.append(msg_al)

        alert_part = None
        if alert_texts:
            num_al = len(alert_texts)
            avisos_line = f"⚠️ {num_al} Alertas (ver sig.)" if num_al > 1 else "⚠️ 1 Alerta (ver sig.)"
            header_alert = "⚠️ [Avisos AEMET]"
            body_alert = "\n".join(alert_texts)
            full_alert = f"{header_alert}\n{body_alert}"
            if len(full_alert.encode("utf-8")) > MESH_MAX_BYTES:
                full_alert = split_messages(full_alert, max_bytes=MESH_MAX_BYTES, max_parts=1)[0]
            alert_part = full_alert
        else:
            avisos_line = "⚠️ 0 Alertas"

        # 5. Información Meteorológica (AEMET o en caché)
        # Se calcula el presupuesto dinámico disponible en el Mensaje 1 para no desbordar 200 bytes
        other_lines = [header_txt]
        if astro_txt:
            other_lines.append(astro_txt)
        other_lines.append(marea_txt)
        other_lines.append(avisos_line)

        prefix_clima = "🌦️ "
        bytes_without_clima = sum(len(l.encode("utf-8")) for l in other_lines) + len(other_lines) + len(prefix_clima.encode("utf-8"))
        available_clima_bytes = max(20, MESH_MAX_BYTES - bytes_without_clima)

        clima_narrative = "Despejado / Sin datos."
        try:
            w = db.aemet_weather_get_latest(province=prov_name, day="hoy")
            if not w:
                w = db.aemet_weather_get_latest(province=prov_name)
            if not w:
                w = db.aemet_weather_get_latest(day="hoy")
            if w and w.get("content"):
                raw_c = w["content"].strip()
                for prefix in ("CÁDIZ ", "CADIZ ", "Cádiz ", "Cadiz ", f"{str(prov_name).upper()} "):
                    if raw_c.startswith(prefix):
                        raw_c = raw_c[len(prefix):].strip()
                        break
                raw_c = sanitize_text(raw_c)
                if "TEMPERATURAS" in raw_c:
                    narrative = raw_c.split("TEMPERATURAS")[0].strip()
                else:
                    narrative = raw_c
                if narrative:
                    clima_narrative = narrative
        except Exception:
            pass

        trimmed_clima = BulletinGenerator._format_weather_text(clima_narrative, available_clima_bytes)
        clima_line = f"{prefix_clima}{trimmed_clima}"

        # 6. Ensamblado final de partes
        part1_lines = [header_txt]
        if astro_txt:
            part1_lines.append(astro_txt)
        part1_lines.append(clima_line)
        part1_lines.append(marea_txt)
        part1_lines.append(avisos_line)

        part1 = "\n".join(part1_lines)
        if len(part1.encode("utf-8")) > MESH_MAX_BYTES:
            part1 = split_messages(part1, max_bytes=MESH_MAX_BYTES, max_parts=1)[0]

        parts = [part1]
        if alert_part:
            parts.append(alert_part)

        return parts

    @staticmethod
    def build_bulletin_text(slot_name: str = "Diario") -> str:
        """Construye el texto unificado del boletín diario."""
        parts = BulletinGenerator.build_bulletin(slot_name=slot_name)
        return "\n\n".join(parts)
