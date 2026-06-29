from __future__ import annotations

"""Predicción de mareas para la ubicación configurada (por defecto Chipiona).

Estrategia (alineada con la filosofía offline del proyecto):

1. Fuente fiable de descarga (para cron → BD):
   - WorldTides API  (si hay TIDES_API_KEY configurada). Datos de estación.
   - Open-Meteo Marine (gratis, sin API key) como fuente por defecto. Se derivan
     pleamares/bajamares de la curva horaria `sea_level_height_msl`.

2. Fallback de cálculo automático (100% offline, sin Internet):
   - Estimación astronómica basada en el tránsito lunar + intervalo de
     establecimiento del puerto (lunitidal interval). Es APROXIMADA: da horas
     orientativas de pleamar/bajamar, sin altura fiable.

Cada extremo es un dict: { 'time': datetime (con tz), 'type': 'high'|'low',
'height': float|None }.
"""

import math
from datetime import datetime, timedelta, timezone, date
from typing import List, Optional, Dict, Any

from Models.Astro import location, sun_times, moon_phase, _tzinfo, _to_julian

try:
    from functions import log_p
except Exception:  # pragma: no cover
    def log_p(*a, **k):
        pass


# Periodo semidiurno lunar medio (M2): 12 h 25.2 min
_TIDAL_PERIOD_H = 12.420601
# Mes sinódico (para amplitud sicigia/cuadratura en la estimación)
_SYNODIC_MONTH = 29.530588853


def _cfg(name: str, default):
    try:
        import env
        v = getattr(env, name, default)
        return v if v not in (None, '') else default
    except Exception:
        return default


# ----------------------------------------------------------------------------
# Detección de extremos a partir de una curva horaria
# ----------------------------------------------------------------------------
def _extremes_from_series(times: List[datetime], heights: List[float]) -> List[Dict[str, Any]]:
    """Detecta pleamares (máximos) y bajamares (mínimos) en una serie horaria.

    Usa interpolación parabólica entre el punto extremo y sus vecinos para
    afinar la hora (la serie es horaria → ±30 min sin afinar).
    """
    extremes: List[Dict[str, Any]] = []
    n = len(heights)
    for i in range(1, n - 1):
        h_prev, h, h_next = heights[i - 1], heights[i], heights[i + 1]
        if h is None or h_prev is None or h_next is None:
            continue
        is_max = h >= h_prev and h >= h_next and (h > h_prev or h > h_next)
        is_min = h <= h_prev and h <= h_next and (h < h_prev or h < h_next)
        if not (is_max or is_min):
            continue
        # Vértice de la parábola que pasa por los 3 puntos (en horas, -0.5..0.5)
        denom = (h_prev - 2 * h + h_next)
        offset = 0.0
        if denom != 0:
            offset = 0.5 * (h_prev - h_next) / denom
            offset = max(-1.0, min(1.0, offset))
        peak_time = times[i] + timedelta(hours=offset)
        peak_height = h - 0.25 * (h_prev - h_next) * offset
        extremes.append({
            'time': peak_time,
            'type': 'high' if is_max else 'low',
            'height': round(peak_height, 2),
        })
    return extremes


# ----------------------------------------------------------------------------
# Fuente 1a: Open-Meteo Marine (gratis, sin key)
# ----------------------------------------------------------------------------
def fetch_open_meteo(lat: float, lon: float, tz_name: str, days: int = 2,
                     timeout: float = 8.0) -> Optional[List[Dict[str, Any]]]:
    """Descarga la curva horaria de nivel del mar y deriva los extremos.

    Devuelve lista de extremos o None si falla / no hay datos.
    """
    try:
        import requests
        url = 'https://marine-api.open-meteo.com/v1/marine'
        params = {
            'latitude': f'{lat:.4f}',
            'longitude': f'{lon:.4f}',
            'hourly': 'sea_level_height_msl',
            'timezone': tz_name,
            'forecast_days': str(max(1, min(7, days))),
        }
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        j = r.json()
        hourly = (j or {}).get('hourly') or {}
        time_strs = hourly.get('time') or []
        vals = hourly.get('sea_level_height_msl') or []
        if not time_strs or not vals or len(time_strs) != len(vals):
            return None
        tz = _tzinfo(tz_name)
        times = [datetime.fromisoformat(t).replace(tzinfo=tz) for t in time_strs]
        ext = _extremes_from_series(times, vals)
        return ext or None
    except Exception as e:
        log_p(f"[tides] open-meteo error: {e}", level="WARN")
        return None


# ----------------------------------------------------------------------------
# Fuente 1b: WorldTides API (requiere TIDES_API_KEY)
# ----------------------------------------------------------------------------
def fetch_worldtides(lat: float, lon: float, tz_name: str, api_key: str,
                     days: int = 2, timeout: float = 8.0) -> Optional[List[Dict[str, Any]]]:
    try:
        import requests
        url = 'https://www.worldtides.info/api/v3'
        params = {
            'extremes': '',
            'lat': f'{lat:.4f}',
            'lon': f'{lon:.4f}',
            'days': str(max(1, min(7, days))),
            'key': api_key,
        }
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        j = r.json()
        items = (j or {}).get('extremes') or []
        if not items:
            return None
        tz = _tzinfo(tz_name)
        out: List[Dict[str, Any]] = []
        for it in items:
            dt = datetime.fromtimestamp(int(it['dt']), tz=timezone.utc).astimezone(tz)
            typ = 'high' if str(it.get('type', '')).lower().startswith('h') else 'low'
            h = it.get('height')
            out.append({'time': dt, 'type': typ, 'height': round(float(h), 2) if h is not None else None})
        return out or None
    except Exception as e:
        log_p(f"[tides] worldtides error: {e}", level="WARN")
        return None


# ----------------------------------------------------------------------------
# Fallback: estimación astronómica (offline, aproximada)
# ----------------------------------------------------------------------------
def astronomical_fallback(lat: float, lon: float, tz_name: str,
                          when: Optional[datetime] = None,
                          window_h: float = 30.0) -> List[Dict[str, Any]]:
    """Estima pleamares/bajamares por tránsito lunar + intervalo del puerto.

    APROXIMADO: sin altura fiable (height=None). Útil solo como respaldo cuando
    no hay datos descargados ni Internet.
    """
    tz = _tzinfo(tz_name)
    if when is None:
        when = datetime.now(tz)
    if when.tzinfo is None:
        when = when.replace(tzinfo=tz)

    # Tránsito solar (mediodía verdadero) en UTC para hoy
    _, transit_utc, _ = sun_times(when.astimezone(tz).date(), lat, lon)
    if transit_utc is None:
        transit_utc = datetime(when.year, when.month, when.day, 12, tzinfo=timezone.utc)

    # Edad lunar → desfase del tránsito lunar respecto al solar (0..24 h)
    age = moon_phase(when)['age']
    lag_h = 24.0 * (age / _SYNODIC_MONTH)

    # Intervalo de establecimiento del puerto (HWI). Configurable; aprox. Cádiz.
    hwi_min = float(_cfg('TIDES_HWI_MIN', 60.0))

    # Pleamar de referencia próxima al tránsito lunar superior de hoy
    base_high = transit_utc + timedelta(hours=lag_h) + timedelta(minutes=hwi_min)

    # Generar una rejilla de pleamares cada ~12.42 h cubriendo la ventana
    start = when.astimezone(timezone.utc) - timedelta(hours=2)
    end = when.astimezone(timezone.utc) + timedelta(hours=window_h)

    # Retroceder/avanzar hasta el primer high water dentro (o justo antes) de la ventana
    period = timedelta(hours=_TIDAL_PERIOD_H)
    k_start = math.floor((start - base_high) / period)
    extremes: List[Dict[str, Any]] = []
    k = k_start
    while True:
        high = base_high + k * period
        if high > end + period:
            break
        low = high + timedelta(hours=_TIDAL_PERIOD_H / 2.0)
        if start <= high <= end:
            extremes.append({'time': high.astimezone(tz), 'type': 'high', 'height': None})
        if start <= low <= end:
            extremes.append({'time': low.astimezone(tz), 'type': 'low', 'height': None})
        k += 1

    extremes.sort(key=lambda e: e['time'])
    return extremes


# ----------------------------------------------------------------------------
# Orquestador
# ----------------------------------------------------------------------------
def compute_tides(days: int = 2, allow_network: bool = True,
                  timeout: float = 8.0) -> Dict[str, Any]:
    """Calcula extremos de marea usando la mejor fuente disponible.

    Devuelve { 'source': str, 'approximate': bool, 'extremes': [...],
    'name': str }.
    - source: 'worldtides' | 'open-meteo' | 'estimacion'
    - timeout: tope por petición HTTP. Desde un comando (que bloquea el hilo de
      recepción) conviene un valor bajo; el cron puede usar el valor por defecto.
    """
    lat, lon, tz_name, name = location()
    api_key = str(_cfg('TIDES_API_KEY', '') or '')

    if allow_network:
        if api_key:
            ext = fetch_worldtides(lat, lon, tz_name, api_key, days=days, timeout=timeout)
            if ext:
                return {'source': 'worldtides', 'approximate': False, 'extremes': ext, 'name': name}
        ext = fetch_open_meteo(lat, lon, tz_name, days=days, timeout=timeout)
        if ext:
            return {'source': 'open-meteo', 'approximate': False, 'extremes': ext, 'name': name}

    ext = astronomical_fallback(lat, lon, tz_name)
    return {'source': 'estimacion', 'approximate': True, 'extremes': ext, 'name': name}


def next_extremes(extremes: List[Dict[str, Any]], now: Optional[datetime] = None,
                  count: int = 4) -> List[Dict[str, Any]]:
    """Filtra los próximos `count` extremos a partir de ahora."""
    tz = None
    if extremes:
        tz = extremes[0]['time'].tzinfo
    if now is None:
        now = datetime.now(tz) if tz else datetime.now()
    upcoming = [e for e in extremes if e['time'] >= now - timedelta(minutes=30)]
    return upcoming[:count]
