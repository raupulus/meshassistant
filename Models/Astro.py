from __future__ import annotations

"""Cálculos astronómicos 100% offline (sin dependencias externas).

Provee orto/ocaso del Sol y fase de la Luna para una posición geográfica.
Pensado para los comandos /sol y /luna del bot Meshtastic, que deben funcionar
sin conexión a Internet.

La posición por defecto es Chipiona (Cádiz). Se puede sobreescribir con las
variables de entorno LOCATION_LAT, LOCATION_LON, LOCATION_TZ y LOCATION_NAME.

Referencias:
- Orto/ocaso: "Sunrise equation" (algoritmo NOAA simplificado).
- Fase lunar: edad lunar respecto a una luna nueva de referencia (mes sinódico).
"""

import math
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Tuple

try:  # zoneinfo disponible en Python 3.9+
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


# ----------------------------------------------------------------------------
# Configuración de ubicación (con defaults para Chipiona)
# ----------------------------------------------------------------------------
def _cfg(name: str, default):
    try:
        import env
        val = getattr(env, name, default)
        return val if val not in (None, '') else default
    except Exception:
        return default


def location() -> Tuple[float, float, str, str]:
    """Devuelve (lat, lon, tz_name, nombre) de la ubicación configurada."""
    lat = float(_cfg('LOCATION_LAT', 36.7361))
    lon = float(_cfg('LOCATION_LON', -6.4358))
    tz = str(_cfg('LOCATION_TZ', 'Europe/Madrid'))
    name = str(_cfg('LOCATION_NAME', 'Chipiona'))
    return lat, lon, tz, name


def _tzinfo(tz_name: str):
    """Devuelve un tzinfo para tz_name; si no hay zoneinfo, usa la hora local."""
    if ZoneInfo is not None:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    # Fallback: zona local del sistema
    return datetime.now().astimezone().tzinfo


# ----------------------------------------------------------------------------
# Utilidades de fecha juliana
# ----------------------------------------------------------------------------
def _to_julian(dt_utc: datetime) -> float:
    """Convierte un datetime UTC a fecha juliana (días)."""
    ts = dt_utc.replace(tzinfo=timezone.utc).timestamp()
    return ts / 86400.0 + 2440587.5


def _from_julian(jd: float) -> datetime:
    """Convierte una fecha juliana a datetime UTC."""
    ts = (jd - 2440587.5) * 86400.0
    return datetime.fromtimestamp(ts, tz=timezone.utc)


# ----------------------------------------------------------------------------
# Sol: orto y ocaso (algoritmo NOAA simplificado)
# ----------------------------------------------------------------------------
def sun_times(day: date, lat: float, lon: float) -> Tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
    """Calcula (orto, tránsito, ocaso) en UTC para el día dado.

    Devuelve datetimes en UTC. Si el Sol no sale o no se pone ese día
    (latitudes extremas), devuelve None en orto/ocaso.
    """
    rad = math.radians
    deg = math.degrees

    # n: número de día desde 2000-01-01 (escala juliana)
    midday = datetime(day.year, day.month, day.day, 12, 0, 0, tzinfo=timezone.utc)
    jd = _to_julian(midday)
    n = jd - 2451545.0 + 0.0008

    # Mediodía solar medio. Con longitud este positiva (lon) el desfase respecto
    # al mediodía de Greenwich es -lon/360 días: lugares al oeste (lon<0) tienen
    # el mediodía solar MÁS TARDE en UTC, como debe ser.
    j_star = n - lon / 360.0

    # Anomalía media del Sol
    M = (357.5291 + 0.98560028 * j_star) % 360.0
    Mr = rad(M)

    # Ecuación del centro
    C = 1.9148 * math.sin(Mr) + 0.0200 * math.sin(2 * Mr) + 0.0003 * math.sin(3 * Mr)

    # Longitud eclíptica
    lam = (M + C + 180.0 + 102.9372) % 360.0
    lamr = rad(lam)

    # Tránsito solar (mediodía verdadero)
    j_transit = 2451545.0 + j_star + 0.0053 * math.sin(Mr) - 0.0069 * math.sin(2 * lamr)

    # Declinación del Sol
    sin_dec = math.sin(lamr) * math.sin(rad(23.4397))
    dec = math.asin(sin_dec)

    # Ángulo horario (altura -0.833° por refracción + radio solar)
    cos_w0 = (math.sin(rad(-0.833)) - math.sin(rad(lat)) * sin_dec) / (math.cos(rad(lat)) * math.cos(dec))

    transit = _from_julian(j_transit)

    if cos_w0 > 1:   # noche polar
        return None, transit, None
    if cos_w0 < -1:  # día polar
        return None, transit, None

    w0 = deg(math.acos(cos_w0))
    j_rise = j_transit - w0 / 360.0
    j_set = j_transit + w0 / 360.0

    return _from_julian(j_rise), transit, _from_julian(j_set)


def sun_info(day: Optional[date] = None) -> dict:
    """Devuelve un dict con orto/ocaso en hora local y duración del día.

    Claves: name, date, sunrise, sunset, transit (datetimes locales o None),
    day_length (timedelta o None).
    """
    lat, lon, tz_name, name = location()
    tz = _tzinfo(tz_name)
    if day is None:
        day = datetime.now(tz).date()

    rise_utc, transit_utc, set_utc = sun_times(day, lat, lon)

    rise_l = rise_utc.astimezone(tz) if rise_utc else None
    set_l = set_utc.astimezone(tz) if set_utc else None
    transit_l = transit_utc.astimezone(tz) if transit_utc else None
    length = (set_utc - rise_utc) if (rise_utc and set_utc) else None

    return {
        'name': name,
        'date': day,
        'sunrise': rise_l,
        'sunset': set_l,
        'transit': transit_l,
        'day_length': length,
    }


# ----------------------------------------------------------------------------
# Luna: fase e iluminación
# ----------------------------------------------------------------------------
# Luna nueva de referencia: 2000-01-06 18:14 UTC (JD 2451550.1)
_KNOWN_NEW_MOON_JD = 2451550.1
_SYNODIC_MONTH = 29.530588853  # días

_PHASE_NAMES = [
    "Luna nueva",
    "Luna creciente",          # creciente cóncava (waxing crescent)
    "Cuarto creciente",
    "Gibosa creciente",
    "Luna llena",
    "Gibosa menguante",
    "Cuarto menguante",
    "Luna menguante",          # menguante (waning crescent)
]


def moon_phase(dt: Optional[datetime] = None) -> dict:
    """Devuelve información de la fase lunar para el instante dado (o ahora).

    Claves: age (días desde luna nueva), illumination (0..1), phase_index (0..7),
    phase_name, waxing (bool, True si va creciendo).
    """
    lat, lon, tz_name, name = location()
    tz = _tzinfo(tz_name)
    if dt is None:
        dt = datetime.now(tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)

    jd = _to_julian(dt.astimezone(timezone.utc))
    age = (jd - _KNOWN_NEW_MOON_JD) % _SYNODIC_MONTH
    if age < 0:
        age += _SYNODIC_MONTH

    # Fracción iluminada (aprox.): (1 - cos(2*pi*age/synodic)) / 2
    phase_angle = 2 * math.pi * age / _SYNODIC_MONTH
    illumination = (1 - math.cos(phase_angle)) / 2.0

    # Índice de fase 0..7 (cada ~3.69 días)
    idx = int((age / _SYNODIC_MONTH) * 8 + 0.5) % 8
    waxing = age < (_SYNODIC_MONTH / 2.0)

    return {
        'age': age,
        'illumination': illumination,
        'phase_index': idx,
        'phase_name': _PHASE_NAMES[idx],
        'waxing': waxing,
    }


def next_phase_dates(dt: Optional[datetime] = None) -> dict:
    """Devuelve fechas locales aproximadas de la próxima luna nueva y llena."""
    lat, lon, tz_name, name = location()
    tz = _tzinfo(tz_name)
    if dt is None:
        dt = datetime.now(tz)
    jd = _to_julian(dt.astimezone(timezone.utc))
    age = (jd - _KNOWN_NEW_MOON_JD) % _SYNODIC_MONTH

    days_to_new = (_SYNODIC_MONTH - age) % _SYNODIC_MONTH
    half = _SYNODIC_MONTH / 2.0
    days_to_full = (half - age) % _SYNODIC_MONTH

    new_moon = (dt + timedelta(days=days_to_new)).astimezone(tz)
    full_moon = (dt + timedelta(days=days_to_full)).astimezone(tz)
    return {'next_new': new_moon, 'next_full': full_moon}
