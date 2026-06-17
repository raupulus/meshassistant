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

# Mapa nombre de provincia -> código oficial AEMET (dos dígitos INE).
# Se usa para la predicción provincial (texto general) y como apoyo a avisos.
PROV_NAME_TO_CODE: Dict[str, str] = {
    "ALAVA": "01", "ARABA": "01", "ALBACETE": "02", "ALICANTE": "03", "ALACANT": "03",
    "ALMERIA": "04", "AVILA": "05", "BADAJOZ": "06", "BALEARES": "07", "ISLAS BALEARES": "07",
    "BARCELONA": "08", "BURGOS": "09", "CACERES": "10", "CADIZ": "11",
    "CASTELLON": "12", "CASTELLO": "12", "CIUDAD REAL": "13", "CORDOBA": "14", "A CORUNA": "15",
    "CORUNA": "15", "CUENCA": "16", "GIRONA": "17", "GERONA": "17", "GRANADA": "18",
    "GUADALAJARA": "19", "GUIPUZCOA": "20", "GIPUZKOA": "20", "HUELVA": "21", "HUESCA": "22",
    "JAEN": "23", "LEON": "24", "LERIDA": "25", "LLEIDA": "25", "LA RIOJA": "26",
    "LUGO": "27", "MADRID": "28", "MALAGA": "29", "MURCIA": "30", "NAVARRA": "31",
    "OURENSE": "32", "PALENCIA": "34", "LAS PALMAS": "35", "PONTEVEDRA": "36",
    "SALAMANCA": "37", "SANTA CRUZ DE TENERIFE": "38", "SEGOVIA": "40", "SEVILLA": "41",
    "SORIA": "42", "TARRAGONA": "43", "TERUEL": "44", "TOLEDO": "45", "VALENCIA": "46",
    "VALLADOLID": "47", "VIZCAYA": "48", "BIZKAIA": "48", "ZAMORA": "49", "ZARAGOZA": "50",
    "CEUTA": "51", "MELILLA": "52",
}


def _normalize_name(s: str) -> str:
    """Quita acentos, colapsa espacios y pasa a mayúsculas."""
    if not s:
        return ''
    nfkd = unicodedata.normalize('NFKD', s)
    s2 = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return ' '.join(s2.split()).upper()


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
