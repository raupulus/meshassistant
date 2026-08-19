from __future__ import annotations

import json
import unicodedata
from typing import Any, Dict, List, Optional

import requests
import env
from functions import log_p

# AEMET OpenData sirve a veces con una cadena de certificados incompleta, lo que
# provoca SSLError en algunos sistemas (la librería de referencia python-aemet usa
# verify=False). Silenciamos el warning porque hacemos fallback controlado a
# verify=False solo si la verificación normal falla.
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


# Base de la API OpenData de AEMET
AEMET_OPENDATA_BASE = 'https://opendata.aemet.es/opendata/api'

# Mapa de provincias y Comunidades Autónomas de España según códigos oficiales INE (2 dígitos)
# y áreas EMMA de AEMET (2 dígitos para CCAA y 4 dígitos para prefijo de zona EMMA_ID).
# Incluye comarcas y términos clave para filtrado preciso en avisos CAP.
PROV_EMMA_MAP: Dict[str, Dict[str, Any]] = {
    # --- ANDALUCÍA (Área EMMA 61) ---
    "ALMERIA": {
        "prov_code": "04", "ccaa_code": "61", "name": "Almería", "ccaa_name": "Andalucía",
        "aliases": ["ALMERIA", "ALMERÍA", "ALMANZORA", "LOS VELEZ", "LOS VÉLEZ", "NACIMIENTO", "CAMPO DE TABERNAS", "TABERNAS", "PONIENTE", "LEVANTE ALMERIENSE", "ALMERIENSE"],
    },
    "CADIZ": {
        "prov_code": "11", "ccaa_code": "61", "name": "Cádiz", "ccaa_name": "Andalucía",
        "aliases": ["CADIZ", "CÁDIZ", "CAMPINA GADITANA", "CAMPIÑA GADITANA", "LITORAL GADITANO", "ESTRECHO", "ESTRECHO - CADIZ", "ESTRECHO - CÁDIZ", "GRAZALEMA", "SIERRA DE GRAZALEMA", "GADITANO", "GADITANA"],
    },
    "CORDOBA": {
        "prov_code": "14", "ccaa_code": "61", "name": "Córdoba", "ccaa_name": "Andalucía",
        "aliases": ["CORDOBA", "CÓRDOBA", "SIERRA Y PEDROCHES", "PEDROCHES", "CAMPINA CORDOBESA", "CAMPIÑA CORDOBESA", "SUBBETICA", "SUBBÉTICA", "SUBBETICA CORDOBESA", "SUBBÉTICA CORDOBESA", "CORDOBESA", "CORDOBES"],
    },
    "GRANADA": {
        "prov_code": "18", "ccaa_code": "61", "name": "Granada", "ccaa_name": "Andalucía",
        "aliases": ["GRANADA", "CUENCA DEL GENIL", "GENIL", "GUADIX Y BAZA", "GUADIX", "BAZA", "NEVADA Y ALPUJARRAS", "NEVADA", "ALPUJARRAS", "COSTA GRANADINA", "GRANADINA"],
    },
    "HUELVA": {
        "prov_code": "21", "ccaa_code": "61", "name": "Huelva", "ccaa_name": "Andalucía",
        "aliases": ["HUELVA", "ARACENA", "SIERRA DE ARACENA", "ANDEVALO Y CONDADO", "ANDÉVALO Y CONDADO", "ANDEVALO", "ANDÉVALO", "CONDADO", "LITORAL ONUBENSE", "ONUBENSE"],
    },
    "JAEN": {
        "prov_code": "23", "ccaa_code": "61", "name": "Jaén", "ccaa_name": "Andalucía",
        "aliases": ["JAEN", "JAÉN", "MORENA Y CONDADO", "SIERRA MORENA", "CAZORLA Y SEGURA", "CAZORLA", "SEGURA", "VALLE DEL GUADALQUIVIR", "CAPITAL Y MONTES DE JAEN", "CAPITAL Y MONTES DE JAÉN", "MONTES DE JAEN", "MONTES DE JAÉN", "JIENNENSE"],
    },
    "MALAGA": {
        "prov_code": "29", "ccaa_code": "61", "name": "Málaga", "ccaa_name": "Andalucía",
        "aliases": ["MALAGA", "MÁLAGA", "RONDA", "SERRANIA DE RONDA", "SERRANÍA DE RONDA", "ANTEQUERA", "SOL Y GUADALHORCE", "GUADALHORCE", "COSTA DEL SOL", "AXARQUIA", "AXARQUÍA", "MALAGUENA", "MALAGUEÑA"],
    },
    "SEVILLA": {
        "prov_code": "41", "ccaa_code": "61", "name": "Sevilla", "ccaa_name": "Andalucía",
        "aliases": ["SEVILLA", "SIERRA NORTE DE SEVILLA", "SIERRA NORTE", "SIERRA SUR DE SEVILLA", "SIERRA SUR", "CAMPINA SEVILLANA", "CAMPIÑA SEVILLANA", "SEVILLANA", "SEVILLANO"],
    },

    # --- ARAGÓN (Área EMMA 62) ---
    "HUESCA": {"prov_code": "22", "ccaa_code": "62", "name": "Huesca", "ccaa_name": "Aragón", "aliases": ["HUESCA", "OSCA", "PIRINEO"]},
    "TERUEL": {"prov_code": "44", "ccaa_code": "62", "name": "Teruel", "ccaa_name": "Aragón", "aliases": ["TERUEL", "ALBARRACIN", "GUDAR", "MAESTRAZGO"]},
    "ZARAGOZA": {"prov_code": "50", "ccaa_code": "62", "name": "Zaragoza", "ccaa_name": "Aragón", "aliases": ["ZARAGOZA", "CINCO VILLAS", "IBERICA"]},

    # --- ASTURIAS (Área EMMA 63) ---
    "ASTURIAS": {"prov_code": "33", "ccaa_code": "63", "name": "Asturias", "ccaa_name": "Asturias", "aliases": ["ASTURIAS", "OVIEDO", "GIJON", "GIJÓN"]},

    # --- BALEARES (Área EMMA 64) ---
    "BALEARES": {"prov_code": "07", "ccaa_code": "64", "name": "Baleares", "ccaa_name": "Islas Baleares", "aliases": ["BALEARES", "ISLAS BALEARES", "MALLORCA", "MENORCA", "IBIZA", "FORMENTERA"]},

    # --- CANARIAS (Área EMMA 65) ---
    "LAS PALMAS": {"prov_code": "35", "ccaa_code": "65", "name": "Las Palmas", "ccaa_name": "Canarias", "aliases": ["LAS PALMAS", "GRAN CANARIA", "LANZAROTE", "FUERTEVENTURA"]},
    "SANTA CRUZ DE TENERIFE": {"prov_code": "38", "ccaa_code": "65", "name": "Santa Cruz de Tenerife", "ccaa_name": "Canarias", "aliases": ["TENERIFE", "SANTA CRUZ DE TENERIFE", "LA PALMA", "LA GOMERA", "EL HIERRO"]},

    # --- CANTABRIA (Área EMMA 66) ---
    "CANTABRIA": {"prov_code": "39", "ccaa_code": "66", "name": "Cantabria", "ccaa_name": "Cantabria", "aliases": ["CANTABRIA", "SANTANDER", "LIEBANA", "LIÉBANA"]},

    # --- CASTILLA Y LEÓN (Área EMMA 67) ---
    "AVILA": {"prov_code": "05", "ccaa_code": "67", "name": "Ávila", "ccaa_name": "Castilla y León", "aliases": ["AVILA", "ÁVILA", "GREDOS"]},
    "BURGOS": {"prov_code": "09", "ccaa_code": "67", "name": "Burgos", "ccaa_name": "Castilla y León", "aliases": ["BURGOS", "DEMANDA", "EBRO"]},
    "LEON": {"prov_code": "24", "ccaa_code": "67", "name": "León", "ccaa_name": "Castilla y León", "aliases": ["LEON", "LEÓN", "BIERZO"]},
    "PALENCIA": {"prov_code": "34", "ccaa_code": "67", "name": "Palencia", "ccaa_name": "Castilla y León", "aliases": ["PALENCIA"]},
    "SALAMANCA": {"prov_code": "37", "ccaa_code": "67", "name": "Salamanca", "ccaa_name": "Castilla y León", "aliases": ["SALAMANCA"]},
    "SEGOVIA": {"prov_code": "40", "ccaa_code": "67", "name": "Segovia", "ccaa_name": "Castilla y León", "aliases": ["SEGOVIA"]},
    "SORIA": {"prov_code": "42", "ccaa_code": "67", "name": "Soria", "ccaa_name": "Castilla y León", "aliases": ["SORIA"]},
    "VALLADOLID": {"prov_code": "47", "ccaa_code": "67", "name": "Valladolid", "ccaa_name": "Castilla y León", "aliases": ["VALLADOLID"]},
    "ZAMORA": {"prov_code": "49", "ccaa_code": "67", "name": "Zamora", "ccaa_name": "Castilla y León", "aliases": ["ZAMORA", "SANABRIA"]},

    # --- CASTILLA-LA MANCHA (Área EMMA 68) ---
    "ALBACETE": {"prov_code": "02", "ccaa_code": "68", "name": "Albacete", "ccaa_name": "Castilla-La Mancha", "aliases": ["ALBACETE", "HELLIN", "HELLÍN", "ALMANSA", "ALCARAZ", "SEGURA"]},
    "CIUDAD REAL": {"prov_code": "13", "ccaa_code": "68", "name": "Ciudad Real", "ccaa_name": "Castilla-La Mancha", "aliases": ["CIUDAD REAL", "MANCHA", "MORENA", "MONTES"]},
    "CUENCA": {"prov_code": "16", "ccaa_code": "68", "name": "Cuenca", "ccaa_name": "Castilla-La Mancha", "aliases": ["CUENCA", "ALCARRIA", "SERRANIA"]},
    "GUADALAJARA": {"prov_code": "19", "ccaa_code": "68", "name": "Guadalajara", "ccaa_name": "Castilla-La Mancha", "aliases": ["GUADALAJARA", "PARAMERAS", "MOLINA"]},
    "TOLEDO": {"prov_code": "45", "ccaa_code": "68", "name": "Toledo", "ccaa_name": "Castilla-La Mancha", "aliases": ["TOLEDO", "VALLE DEL TAJO"]},

    # --- CATALUÑA (Área EMMA 69) ---
    "BARCELONA": {"prov_code": "08", "ccaa_code": "69", "name": "Barcelona", "ccaa_name": "Cataluña", "aliases": ["BARCELONA", "LITORAL", "PRELITORAL", "DEPRESSIO"]},
    "GIRONA": {"prov_code": "17", "ccaa_code": "69", "name": "Girona", "ccaa_name": "Cataluña", "aliases": ["GIRONA", "GERONA", "EMPORDÀ", "EMPORDA", "PIRINEU"]},
    "LLEIDA": {"prov_code": "25", "ccaa_code": "69", "name": "Lleida", "ccaa_name": "Cataluña", "aliases": ["LLEIDA", "LERIDA", "LÉRIDA", "ARAN", "PIRINEU"]},
    "TARRAGONA": {"prov_code": "43", "ccaa_code": "69", "name": "Tarragona", "ccaa_name": "Cataluña", "aliases": ["TARRAGONA", "EBRO", "DELTA"]},

    # --- EXTREMADURA (Área EMMA 70) ---
    "BADAJOZ": {"prov_code": "06", "ccaa_code": "70", "name": "Badajoz", "ccaa_name": "Extremadura", "aliases": ["BADAJOZ", "VEGAS DEL GUADIANA", "BARROS", "SERENA", "SUR"]},
    "CACERES": {"prov_code": "10", "ccaa_code": "70", "name": "Cáceres", "ccaa_name": "Extremadura", "aliases": ["CACERES", "CÁCERES", "TAJO", "ALAGON", "ALAGÓN", "NORTE", "VILLUERCAS", "IBORES"]},

    # --- GALICIA (Área EMMA 71) ---
    "A CORUNA": {"prov_code": "15", "ccaa_code": "71", "name": "A Coruña", "ccaa_name": "Galicia", "aliases": ["A CORUNA", "A CORUÑA", "CORUNA", "CORUÑA", "SANTIAGO"]},
    "LUGO": {"prov_code": "27", "ccaa_code": "71", "name": "Lugo", "ccaa_name": "Galicia", "aliases": ["LUGO", "MARIÑA", "MARINA", "MINO", "MIÑO", "SURESTE"]},
    "OURENSE": {"prov_code": "32", "ccaa_code": "71", "name": "Ourense", "ccaa_name": "Galicia", "aliases": ["OURENSE", "ORENSE", "VALDEORRAS", "MINO", "MIÑO"]},
    "PONTEVEDRA": {"prov_code": "36", "ccaa_code": "71", "name": "Pontevedra", "ccaa_name": "Galicia", "aliases": ["PONTEVEDRA", "RIAS BAIXAS", "RÍAS BAIXAS", "VIGO", "MINO", "MIÑO"]},

    # --- MADRID (Área EMMA 72) ---
    "MADRID": {"prov_code": "28", "ccaa_code": "72", "name": "Madrid", "ccaa_name": "Madrid", "aliases": ["MADRID", "SIERRA DE MADRID", "METROPOLITANA", "SUR", "VEGAS", "HENARES"]},

    # --- MURCIA (Área EMMA 73) ---
    "MURCIA": {"prov_code": "30", "ccaa_code": "73", "name": "Murcia", "ccaa_name": "Región de Murcia", "aliases": ["MURCIA", "VEGA DEL SEGURA", "ALTIPLANO", "NOROESTE", "VALLE DEL GUADALENTIN", "VALLE DEL GUADALENTÍN", "AGUILAS", "ÁGUILAS", "CAMPO DE CARTAGENA", "CARTAGENA", "MAZARRON", "MAZARRÓN"]},

    # --- NAVARRA (Área EMMA 74) ---
    "NAVARRA": {"prov_code": "31", "ccaa_code": "74", "name": "Navarra", "ccaa_name": "Navarra", "aliases": ["NAVARRA", "PAMPLONA", "PIRINEO", "RIBERA", "CENTRO"]},

    # --- PAÍS VASCO (Área EMMA 75) ---
    "ALAVA": {"prov_code": "01", "ccaa_code": "75", "name": "Álava", "ccaa_name": "País Vasco", "aliases": ["ALAVA", "ÁLAVA", "ARABA", "VITORIA", "LLANADA", "RIBERA"]},
    "GUIPUZCOA": {"prov_code": "20", "ccaa_code": "75", "name": "Guipúzcoa", "ccaa_name": "País Vasco", "aliases": ["GUIPUZCOA", "GUIPÚZCOA", "GIPUZKOA", "SAN SEBASTIAN", "SAN SEBASTIÁN", "DONOSTIA"]},
    "VIZCAYA": {"prov_code": "48", "ccaa_code": "75", "name": "Vizcaya", "ccaa_name": "País Vasco", "aliases": ["VIZCAYA", "BIZKAIA", "BILBAO"]},

    # --- LA RIOJA (Área EMMA 76) ---
    "LA RIOJA": {"prov_code": "26", "ccaa_code": "76", "name": "La Rioja", "ccaa_name": "La Rioja", "aliases": ["LA RIOJA", "RIOJA", "LOGRONO", "LOGROÑO", "RIBERA DEL EBRO", "IBERICA"]},

    # --- COMUNITAT VALENCIANA (Área EMMA 77) ---
    "ALICANTE": {"prov_code": "03", "ccaa_code": "77", "name": "Alicante", "ccaa_name": "Comunitat Valenciana", "aliases": ["ALICANTE", "ALACANT", "LITORAL", "INTERIOR"]},
    "CASTELLON": {"prov_code": "12", "ccaa_code": "77", "name": "Castellón", "ccaa_name": "Comunitat Valenciana", "aliases": ["CASTELLON", "CASTELLÓN", "CASTELLO", "CASTELLÓ", "MAESTRAZGO"]},
    "VALENCIA": {"prov_code": "46", "ccaa_code": "77", "name": "Valencia", "ccaa_name": "Comunitat Valenciana", "aliases": ["VALENCIA", "VALÈNCIA"]},

    # --- CIUDADES AUTÓNOMAS (Áreas EMMA 78 y 79) ---
    "CEUTA": {"prov_code": "51", "ccaa_code": "78", "name": "Ceuta", "ccaa_name": "Ceuta", "aliases": ["CEUTA"]},
    "MELILLA": {"prov_code": "52", "ccaa_code": "79", "name": "Melilla", "ccaa_name": "Melilla", "aliases": ["MELILLA"]},
}

# Mapa invertido CCAA -> Área EMMA (para cuando se especifica CCAA completa como Galicia o Andalucía)
CCAA_NAME_TO_CODE: Dict[str, str] = {
    "ANDALUCIA": "61", "ARAGON": "62", "ASTURIAS": "63", "BALEARES": "64", "ISLAS BALEARES": "64",
    "CANARIAS": "65", "CANTABRIA": "66", "CASTILLA Y LEON": "67", "CASTILLA-LA MANCHA": "68",
    "CATALUNA": "69", "EXTREMADURA": "70", "GALICIA": "71", "MADRID": "72", "MURCIA": "73",
    "NAVARRA": "74", "PAIS VASCO": "75", "EUSKADI": "75", "LA RIOJA": "76",
    "COMUNITAT VALENCIANA": "77", "VALENCIA": "77", "CEUTA": "78", "MELILLA": "79",
}

# Compatibilidad hacia atrás: mapa nombre provincia -> código INE (dos dígitos)
PROV_NAME_TO_CODE: Dict[str, str] = {
    k: v["prov_code"] for k, v in PROV_EMMA_MAP.items()
}
# Alias adicionales
PROV_NAME_TO_CODE.update({
    "ARABA": "01", "ALACANT": "03", "ISLAS BALEARES": "07", "CASTELLO": "12",
    "CORUNA": "15", "A CORUNA": "15", "GERONA": "17", "GIPUZKOA": "20",
    "LERIDA": "25", "LLEIDA": "25", "BIZKAIA": "48",
})


def _normalize_name(s: str) -> str:
    """Quita acentos, colapsa espacios y pasa a mayúsculas."""
    if not s:
        return ''
    nfkd = unicodedata.normalize('NFKD', s)
    s2 = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return ' '.join(s2.split()).upper()


def get_province_emma_info(name_or_code: str) -> Optional[Dict[str, Any]]:
    """Obtiene la información EMMA (código INE, código C.A., prefijo EMMA y alias)
    a partir del nombre de provincia o de su código INE de dos dígitos.
    """
    raw = (name_or_code or '').strip()
    if not raw:
        return None

    # Búsqueda por código INE directo (2 dígitos)
    if raw.isdigit() and len(raw) == 2:
        for prov_key, info in PROV_EMMA_MAP.items():
            if info["prov_code"] == raw:
                res = dict(info)
                res["key"] = prov_key
                res["emma_prefix"] = f"{info['ccaa_code']}{info['prov_code']}"
                return res

    norm = _normalize_name(raw)

    # 1. Coincidencia directa por clave
    if norm in PROV_EMMA_MAP:
        info = dict(PROV_EMMA_MAP[norm])
        info["key"] = norm
        info["emma_prefix"] = f"{info['ccaa_code']}{info['prov_code']}"
        return info

    # 2. Coincidencia en PROV_NAME_TO_CODE
    code = PROV_NAME_TO_CODE.get(norm)
    if code:
        for prov_key, info in PROV_EMMA_MAP.items():
            if info["prov_code"] == code:
                res = dict(info)
                res["key"] = prov_key
                res["emma_prefix"] = f"{info['ccaa_code']}{info['prov_code']}"
                return res

    # 3. Coincidencia por alias
    for prov_key, info in PROV_EMMA_MAP.items():
        if any(norm == _normalize_name(a) for a in info.get("aliases", [])):
            res = dict(info)
            res["key"] = prov_key
            res["emma_prefix"] = f"{info['ccaa_code']}{info['prov_code']}"
            return res

    # 4. Coincidencia por CCAA completa (p. ej. "Andalucía" o "Galicia")
    ccaa_code = CCAA_NAME_TO_CODE.get(norm)
    if ccaa_code:
        return {
            "prov_code": None,
            "ccaa_code": ccaa_code,
            "name": raw.title(),
            "ccaa_name": raw.title(),
            "emma_prefix": ccaa_code,
            "aliases": [norm],
            "key": norm,
            "is_ccaa": True,
        }

    return None


class Aemet:
    """Cliente para la API de AEMET y utilidades de publicación.

    - Usa variables de entorno definidas en env.py:
      - AEMET_API_KEY (str)
      - AEMET_CHANNELS (List[int])
      - AEMET_PROVINCE (str)
      - AEMET_PERIOD (str: Hour|Three_hour|Six_hour|Twelve_hour|Day)
      - AEMET_HOUR_MIN (int 0-23)
      - AEMET_HOUR_MAX (int 0-23)

    - Exposición de métodos HTTP genéricos como en Models/Api, pero con cabecera `api_key`.
    - Timeout: 5s
    - Reintentos: 2
    """

    def __init__(self, timeout: float = 5.0, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = max(1, int(retries))
        self.api_key: Optional[str] = getattr(env, 'AEMET_API_KEY', None) or None

        # Configuración
        self.channels: List[int] = list(getattr(env, 'AEMET_CHANNELS', []) or [])
        self.province: str = getattr(env, 'AEMET_PROVINCE', '')
        self.period: str = getattr(env, 'AEMET_PERIOD', 'Hour')
        self.hour_min: int = int(getattr(env, 'AEMET_HOUR_MIN', 0) or 0)
        self.hour_max: int = int(getattr(env, 'AEMET_HOUR_MAX', 23) or 23)

        # Ciudad/municipio para la predicción concreta (fallback si la provincia
        # no estuviera disponible en la API). El código INE de 5 dígitos es
        # opcional: si no se indica, se intenta resolver por nombre conocido.
        self.city: str = getattr(env, 'AEMET_CITY', 'Chipiona') or 'Chipiona'
        self.city_code: str = str(getattr(env, 'AEMET_CITY_CODE', '') or '').strip()

    # ----------- HTTP helpers -----------
    def _headers(self) -> Dict[str, str]:
        h = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        if self.api_key:
            # AEMET suele usar cabecera `api_key` o query param; aquí usamos header.
            h['api_key'] = self.api_key
        return h

    def upload(self, url: str, data: Optional[Dict[str, Any]] = None) -> Any:
        return self._request('POST', url, data)

    def download(self, url: str, data: Optional[Dict[str, Any]] = None) -> Any:
        # Preferimos POST para payload; si la API requiere GET con params, pasar URL ya parametrizada.
        return self._request('POST', url, data)

    def _request(self, method: str, url: str, data: Optional[Dict[str, Any]]) -> Any:
        last_err: Optional[Exception] = None
        payload = json.dumps(data) if data is not None else None
        for _ in range(self.retries):
            try:
                resp = requests.request(
                    method=method.upper(),
                    url=url,
                    headers=self._headers(),
                    data=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                if resp.content:
                    # Intentar JSON; si falla, devolver texto
                    try:
                        return resp.json()
                    except Exception:
                        return resp.text
                return None
            except Exception as e:
                last_err = e
        if last_err:
            raise last_err
        return None

    # ----------- Reglas de publicación -----------
    @staticmethod
    def period_to_minutes(period: str) -> int:
        p = (period or '').lower()
        if p in ('hour', '1h'):
            return 60
        if p in ('three_hour', '3h', 'three-hour', 'threehour'):
            return 180
        if p in ('six_hour', '6h', 'six-hour', 'sixhour'):
            return 360
        if p in ('twelve_hour', '12h', 'twelve-hour', 'twelvehour'):
            return 720
        if p in ('day', '1d', 'daily'):
            return 1440
        # Por defecto, 60 min
        return 60

    def is_within_hour_window(self, now_hour: int) -> bool:
        # AEMET_HOUR_MIN <= hora actual <= AEMET_HOUR_MAX
        hmin = max(0, min(23, int(self.hour_min)))
        hmax = max(0, min(23, int(self.hour_max)))
        if hmin <= hmax:
            return hmin <= now_hour <= hmax
        # Ventana que cruza medianoche, p.ej. 22 -> 6
        return now_hour >= hmin or now_hour <= hmax

    # ----------- Metadatos EMMA y provincia -----------
    def get_emma_info(self) -> Optional[Dict[str, Any]]:
        """Devuelve la información EMMA (código CCAA, código provincia, prefijo y alias)
        de la provincia configurada en AEMET_PROVINCE.
        """
        return get_province_emma_info(self.province)

    def ccaa_code(self) -> Optional[str]:
        """Devuelve el código EMMA (2 dígitos) de la Comunidad Autónoma correspondiente."""
        info = self.get_emma_info()
        return info.get("ccaa_code") if info else None

    # ----------- Predicción meteorológica (clima) -----------
    def province_code(self) -> Optional[str]:
        """Devuelve el código INE (2 dígitos) de la provincia configurada.

        Acepta que AEMET_PROVINCE sea ya un código de 2 dígitos o un nombre
        (con o sin tildes). Devuelve None si no se puede resolver.
        """
        raw = (self.province or '').strip()
        if not raw:
            return None
        if raw.isdigit() and len(raw) == 2:
            return raw
        return PROV_NAME_TO_CODE.get(_normalize_name(raw))

    def resolve_city_code(self) -> Optional[str]:
        """Devuelve el código INE (5 dígitos) del municipio configurado.

        Prioriza AEMET_CITY_CODE; si no, intenta un pequeño mapa de municipios
        conocidos por nombre normalizado. Devuelve None si no se puede resolver.
        """
        if self.city_code and self.city_code.isdigit() and len(self.city_code) == 5:
            return self.city_code
        # Mapa mínimo ampliable: nombre municipio normalizado -> código INE (5)
        KNOWN_CITIES = {
            'CHIPIONA': '11016',
        }
        return KNOWN_CITIES.get(_normalize_name(self.city or ''))

    # AEMET sirve con cadena de certificados incompleta en muchos sistemas. Una
    # vez detectado el fallo SSL en el proceso, vamos directos a verify=False para
    # no malgastar un handshake fallido en cada petición (importante en la Pi).
    _ssl_insecure = False

    def _http_get(self, url: str, *, headers: Optional[Dict[str, str]] = None,
                  params: Optional[Dict[str, str]] = None, timeout: Optional[float] = None):
        """GET con reintento SSL: primero verify=True; si falla por SSL, verify=False.

        Devuelve el objeto Response. Lanza la excepción si no es problema de SSL.
        """
        to = timeout or self.timeout
        if Aemet._ssl_insecure:
            return requests.get(url, headers=headers, params=params, timeout=to, verify=False)
        try:
            return requests.get(url, headers=headers, params=params, timeout=to)
        except requests.exceptions.SSLError as e:
            log_p(f"[aemet] SSLError en {url}; usando verify=False en adelante ({e})", level="WARN")
            Aemet._ssl_insecure = True
            return requests.get(url, headers=headers, params=params, timeout=to, verify=False)

    def _opendata_two_step(self, path_url: str, *, raw: bool = False) -> Optional[Any]:
        """Realiza el patrón OpenData de dos pasos.

        1) GET a `path_url` con api_key (cabecera y query) → JSON {estado,datos}.
        2) GET a la URL de `datos` (documento real) → devuelve su texto.

        Devuelve el texto del documento (str) o None si falla/estado != 200.
        Con raw=True intenta parsear el documento como JSON.
        """
        if not self.api_key:
            log_p("[aemet] _opendata_two_step: sin api_key", level="WARN")
            return None
        try:
            headers = {'Accept': 'application/json', 'api_key': self.api_key}
            params = {'api_key': self.api_key}
            r1 = self._http_get(path_url, headers=headers, params=params)
            log_p(f"[aemet] paso1 {path_url} -> {r1.status_code} ct={r1.headers.get('Content-Type')}")
            r1.raise_for_status()
            try:
                j = r1.json()
            except Exception:
                log_p(f"[aemet] paso1 respuesta no-JSON: {r1.text[:200]}", level="WARN")
                return None
            if not isinstance(j, dict):
                return None
            estado = j.get('estado')
            if estado is not None and int(str(estado)) != 200:
                log_p(f"[aemet] paso1 estado={estado} desc={j.get('descripcion')}", level="WARN")
                return None
            datos_url = j.get('datos')
            if not datos_url:
                log_p(f"[aemet] paso1 sin campo 'datos': {j}", level="WARN")
                return None
            r2 = self._http_get(datos_url, timeout=max(self.timeout, 10.0))
            log_p(f"[aemet] paso2 -> {r2.status_code} ct={r2.headers.get('Content-Type')} len={len(r2.content)}")
            r2.raise_for_status()
            # AEMET sirve a menudo en ISO-8859-15/latin-1; respetar codificación
            if not r2.encoding or r2.encoding.lower() == 'iso-8859-1':
                r2.encoding = 'ISO-8859-15'
            if raw:
                try:
                    return r2.json()
                except Exception:
                    return r2.text
            return r2.text
        except Exception as e:
            log_p(f"[aemet] _opendata_two_step error: {e.__class__.__name__}: {e}", level="WARN")
            return None

    def fetch_province_forecast(self, day: str = 'hoy') -> Optional[str]:
        """Predicción general (texto) de la provincia configurada para hoy.

        Endpoint: /prediccion/provincia/{dia}/{codigo}. Devuelve el texto plano,
        ya limpio de la cabecera (agencia, fecha de elaboración, "válida para…"),
        de modo que solo queda el pronóstico. None si la API no devuelve datos.
        """
        code = self.province_code()
        if not code:
            return None
        url = f"{AEMET_OPENDATA_BASE}/prediccion/provincia/{day}/{code}"
        text = self._opendata_two_step(url)
        if not text:
            return None
        cleaned = self._clean_province_text(text)
        return cleaned or None

    @staticmethod
    def _clean_province_text(text: str) -> str:
        """Quita la cabecera burocrática de la predicción provincial de AEMET.

        El texto llega con líneas tipo "AGENCIA ESTATAL DE METEOROLOGÍA",
        "PREDICCIÓN PARA LA PROVINCIA DE ...", "DÍA ... HORA OFICIAL" y
        "PREDICCIÓN VÁLIDA PARA ...". Nos quedamos con el pronóstico real (lo que
        va tras "PREDICCIÓN VÁLIDA PARA ..."), que es lo útil en un mensaje corto.
        """
        if not text:
            return ''
        # Normalizar saltos (AEMET usa \r\r\n) y trocear en líneas no vacías
        norm = text.replace('\r', '\n')
        lines = [ln.strip() for ln in norm.split('\n') if ln.strip()]
        if not lines:
            return ''

        def _up(s: str) -> str:
            return _normalize_name(s)

        # Buscar el marcador "PREDICCION VALIDA PARA ..." y quedarnos con lo de después
        start = 0
        for i, ln in enumerate(lines):
            if _up(ln).startswith('PREDICCION VALIDA PARA'):
                start = i + 1
                break

        body_lines = lines[start:] if start else lines

        # Filtrar cualquier línea de cabecera residual
        import re
        skip_prefixes = (
            'AGENCIA ESTATAL',
            'PREDICCION PARA LA PROVINCIA',
            'PREDICCION VALIDA PARA',
        )
        kept: List[str] = []
        for ln in body_lines:
            up = _up(ln)
            if up.startswith(skip_prefixes):
                continue
            if re.match(r'^DIA \d+ DE .* HORA OFICIAL', up):
                continue
            kept.append(ln)

        result = ' '.join(' '.join(kept).split())
        return result.strip()

    def fetch_city_forecast(self) -> Optional[str]:
        """Predicción diaria del municipio (AEMET_CITY) formateada compacta.

        Endpoint: /prediccion/especifica/municipio/diaria/{codigo5}.
        Devuelve un texto breve con el día de hoy (temperaturas, cielo y prob.
        de lluvia) o None si no está disponible.
        """
        code = self.resolve_city_code()
        if not code:
            return None
        url = f"{AEMET_OPENDATA_BASE}/prediccion/especifica/municipio/diaria/{code}"
        data = self._opendata_two_step(url, raw=True)
        return self._format_city_forecast(data)

    def fetch_city_forecast_multi(self, days: int = 4) -> Optional[str]:
        """Predicción del municipio (AEMET_CITY) para varios días, compacta.

        Endpoint: /prediccion/especifica/municipio/diaria/{codigo5}.
        Devuelve un texto breve con hasta `days` días (cada uno: día, temperaturas,
        cielo y prob. de lluvia) o None si no está disponible.
        """
        code = self.resolve_city_code()
        if not code:
            return None
        url = f"{AEMET_OPENDATA_BASE}/prediccion/especifica/municipio/diaria/{code}"
        data = self._opendata_two_step(url, raw=True)
        return self._format_city_forecast_multi(data, days=days)

    def _format_city_forecast_multi(self, data: Any, days: int = 4) -> Optional[str]:
        """Convierte el JSON de predicción municipal en un texto breve multi-día."""
        try:
            if isinstance(data, str):
                data = json.loads(data)
            root = data[0] if isinstance(data, list) and data else data
            if not isinstance(root, dict):
                return None

            nombre = root.get('nombre') or self.city
            dias = (((root.get('prediccion') or {}).get('dia')) or [])
            if not dias:
                return None

            # Nombres de día de la semana en español a partir de la fecha
            import datetime as _dt
            dow = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']

            partes_dias: List[str] = []
            for d in dias[:max(1, min(7, days))]:
                if not isinstance(d, dict):
                    continue
                fecha = d.get('fecha') or ''
                etiqueta = fecha[:10]
                try:
                    dt = _dt.date.fromisoformat(fecha[:10])
                    etiqueta = f"{dow[dt.weekday()]} {dt.day}"
                except Exception:
                    pass

                temp = d.get('temperatura') or {}
                tmax = temp.get('maxima')
                tmin = temp.get('minima')

                cielo = ''
                for ec in (d.get('estadoCielo') or []):
                    desc = (ec or {}).get('descripcion') or ''
                    if desc.strip():
                        cielo = desc.strip()
                        break

                probs = []
                for pp in (d.get('probPrecipitacion') or []):
                    v = (pp or {}).get('value')
                    try:
                        if v is not None and str(v) != '':
                            probs.append(int(float(v)))
                    except Exception:
                        pass
                prob = max(probs) if probs else None

                campos: List[str] = [etiqueta]
                if tmin is not None and tmax is not None:
                    campos.append(f"{tmin}-{tmax}°C")
                if cielo:
                    campos.append(cielo)
                if prob is not None:
                    campos.append(f"lluvia {prob}%")
                partes_dias.append(' '.join(campos))

            if not partes_dias:
                return None
            return f"{nombre}: " + ' | '.join(partes_dias)
        except Exception:
            return None

    def _format_city_forecast(self, data: Any) -> Optional[str]:
        """Convierte el JSON de predicción municipal en un texto breve."""
        try:
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, list):
                root = data[0] if data else None
            else:
                root = data
            if not isinstance(root, dict):
                return None

            nombre = root.get('nombre') or self.city
            dias = (((root.get('prediccion') or {}).get('dia')) or [])
            if not dias:
                return None
            d0 = dias[0] if isinstance(dias[0], dict) else {}

            temp = d0.get('temperatura') or {}
            tmax = temp.get('maxima')
            tmin = temp.get('minima')

            # Estado del cielo: primer valor con descripción no vacía
            cielo = ''
            for ec in (d0.get('estadoCielo') or []):
                desc = (ec or {}).get('descripcion') or ''
                if desc.strip():
                    cielo = desc.strip()
                    break

            # Probabilidad de precipitación: máximo de los tramos disponibles
            probs = []
            for pp in (d0.get('probPrecipitacion') or []):
                v = (pp or {}).get('value')
                try:
                    if v is not None and str(v) != '':
                        probs.append(int(float(v)))
                except Exception:
                    pass
            prob = max(probs) if probs else None

            partes: List[str] = [str(nombre)]
            if tmin is not None and tmax is not None:
                partes.append(f"{tmin}-{tmax}°C")
            if cielo:
                partes.append(cielo)
            if prob is not None:
                partes.append(f"lluvia {prob}%")
            text = '. '.join([p for p in partes if p]).strip()
            return text or None
        except Exception:
            return None
