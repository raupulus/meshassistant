from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import requests
import env


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
