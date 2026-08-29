import re
from functions import log_p, reply_long
from datetime import datetime, timedelta
from Models.Database import Database
from Models.Aemet import Aemet


def _parse_prevision_args(args: list) -> tuple:
    """Parsea los argumentos de /prevision.

    Devuelve una tupla:
      - ('daily', int_days) -> entre 1 y 7
      - ('tomorrow', None)
      - ('hourly', int_hours) -> entre 1 y 12
    """
    if not args:
        return ('daily', 3)

    raw = ' '.join(args).lower().strip()

    if 'mañana' in raw or 'manana' in raw:
        return ('tomorrow', None)

    # Detección de horas: "6 horas", "6h", "horas 6", "12 horas", etc.
    m_h = re.search(r'(\d+)\s*(?:h|horas?)|horas?\s*(\d+)', raw)
    if m_h or 'hora' in raw:
        val = 6
        if m_h:
            num_str = m_h.group(1) or m_h.group(2)
            if num_str:
                try:
                    val = int(num_str)
                except Exception:
                    pass
        clamped_h = max(1, min(12, val))
        return ('hourly', clamped_h)

    # Detección de días: "4 dias", "4d", "dias 4", "7 dias", etc.
    m_d = re.search(r'(\d+)\s*(?:d|dias?)|dias?\s*(\d+)', raw)
    if m_d or 'dia' in raw:
        val = 3
        if m_d:
            num_str = m_d.group(1) or m_d.group(2)
            if num_str:
                try:
                    val = int(num_str)
                except Exception:
                    pass
        clamped_d = max(1, min(7, val))
        return ('daily', clamped_d)

    # Si se pasa un número suelto, ej. "/prevision 5"
    if raw.isdigit():
        val = int(raw)
        return ('daily', max(1, min(7, val)))

    return ('daily', 3)


def prevision_callback(interface, args, msg, metadata):
    """/prevision — Predicción meteorológica flexible de AEMET.

    - Sin argumentos: 3 días (por defecto).
    - /prevision mañana: predicción específica del día siguiente.
    - /prevision <1-7> dias: previsión de 1 a 7 días.
    - /prevision <1-12> horas: tramos horarios para las próximas 1 a 12 horas.
    """
    log_p(f"Comando /prevision recibido con args={args}")
    db = Database()
    aemet = Aemet()
    mode, param = _parse_prevision_args(args)

    text = None

    # ---------- CASO 1: HORARIA (1 a 12 horas) ----------
    if mode == 'hourly':
        hours = param or 6
        rec_h = db.aemet_forecast_hourly_get_latest()
        if rec_h and rec_h.get('data'):
            text = aemet.format_hourly_forecast(rec_h['data'], hours=hours)

        if not text:
            # Fallback on-demand con timeout defensivo
            try:
                data_h = aemet.fetch_hourly_forecast()
                if data_h:
                    text = aemet.format_hourly_forecast(data_h, hours=hours)
                    summary_24h = aemet.format_hourly_forecast(data_h, hours=12)
                    db.aemet_forecast_hourly_insert(
                        city_code=aemet.resolve_city_code() or '11016',
                        city_name=aemet.city or 'Chipiona',
                        province=aemet.province or 'Cádiz',
                        data_json=data_h,
                        summary_24h=summary_24h,
                    )
            except Exception as e:
                log_p(f"Error previsión horaria on-demand: {e}", level="WARN")

    # ---------- CASO 2: MAÑANA ----------
    elif mode == 'tomorrow':
        rec_d = db.aemet_forecast_daily_get_latest()
        if rec_d and rec_d.get('data'):
            text = aemet.format_tomorrow_forecast(rec_d['data'])

        if not text:
            # Fallback texto provincial de mañana si está en BD
            rec_w = db.aemet_weather_get_latest(day='manana')
            if rec_w and rec_w.get('content'):
                text = f"🌦️ Cádiz (Mañana): {rec_w.get('content')}"

        if not text:
            # Fallback on-demand
            try:
                data_d = aemet.fetch_daily_forecast()
                if data_d:
                    text = aemet.format_tomorrow_forecast(data_d)
                    db.aemet_forecast_daily_insert(
                        city_code=aemet.resolve_city_code() or '11016',
                        city_name=aemet.city or 'Chipiona',
                        province=aemet.province or 'Cádiz',
                        data_json=data_d,
                        summary_3d=aemet.format_daily_forecast(data_d, days=3),
                        summary_7d=aemet.format_daily_forecast(data_d, days=7),
                    )
            except Exception as e:
                log_p(f"Error previsión mañana on-demand: {e}", level="WARN")

    # ---------- CASO 3: DIARIA MULTI-DÍA (1 a 7 días) ----------
    else:
        days = param or 3
        rec_d = db.aemet_forecast_daily_get_latest()
        if rec_d and rec_d.get('data'):
            text = aemet.format_daily_forecast(rec_d['data'], days=days)

        if not text:
            # Fallback on-demand
            try:
                data_d = aemet.fetch_daily_forecast()
                if data_d:
                    text = aemet.format_daily_forecast(data_d, days=days)
                    db.aemet_forecast_daily_insert(
                        city_code=aemet.resolve_city_code() or '11016',
                        city_name=aemet.city or 'Chipiona',
                        province=aemet.province or 'Cádiz',
                        data_json=data_d,
                        summary_3d=aemet.format_daily_forecast(data_d, days=3),
                        summary_7d=aemet.format_daily_forecast(data_d, days=7),
                    )
            except Exception as e:
                log_p(f"Error previsión multi-día on-demand: {e}", level="WARN")

    # ---------- FALLBACK RESIDUAL ----------
    if not text:
        # Último recurso: lo que haya en aemet_weather
        rec_w = db.aemet_weather_get_latest()
        if rec_w and rec_w.get('content'):
            text = f"🌦️ Previsión: {rec_w.get('content')}"

    if not text:
        interface.reply_to_message('Sin previsión disponible todavía. Inténtalo más tarde.', metadata)
        return

    reply_long(interface, metadata, text)
