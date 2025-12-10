from __future__ import annotations

import json
from typing import Any, Dict, Optional

import requests


class Api:
    """Cliente HTTP sencillo para enviar/recibir JSON con reintentos y timeout fijo.

    - Timeout: 5s
    - Reintentos: 2
    - Cabecera opcional con API key si se establece con `set_apikey()`.
    """

    def __init__(self, timeout: float = 5.0, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = max(1, int(retries))
        self.api_key: Optional[str] = None

    def set_apikey(self, key: Optional[str]) -> None:
        """Configura la API key para incluirla en los headers si no es None."""
        self.api_key = key

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, method: str, url: str, data: Optional[Dict[str, Any]] = None) -> Any:
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
                    return resp.json()
                return None
            except Exception as e:
                last_err = e
        # Exhausted retries
        if last_err:
            raise last_err
        return None

    def upload(self, url: str, data: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("POST", url, data)

    def download(self, url: str, data: Optional[Dict[str, Any]] = None) -> Any:
        # Prefer POST for payload; if server expects GET with params, adjust calling side
        return self._request("POST", url, data)
