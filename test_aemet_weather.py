#!/usr/bin/env python3
"""Diagnóstico en vivo de la descarga de clima de AEMET.

Ejecútalo donde haya salida a Internet (tu equipo o la Raspberry):

    python3 test_aemet_weather.py

Usa la configuración de env.py. No escribe en la base de datos. Imprime el
detalle de cada paso (status HTTP, cuerpo, errores SSL) para depurar.
"""
import env
# Forzar logs aunque DEBUG esté a False en env.py
env.DEBUG = True

import requests
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

from Models.Aemet import Aemet, AEMET_OPENDATA_BASE


def probe(url, api_key):
    """Prueba un endpoint paso 1 + paso 2, con verify=True y, si falla, False."""
    for verify in (True, False):
        try:
            print(f"\n  GET (verify={verify}) {url}")
            r = requests.get(
                url,
                headers={'Accept': 'application/json', 'api_key': api_key},
                params={'api_key': api_key},
                timeout=15,
                verify=verify,
            )
            print(f"    status={r.status_code} ct={r.headers.get('Content-Type')}")
            print(f"    body[:300]={r.text[:300]!r}")
            if r.status_code != 200:
                continue
            j = r.json()
            datos = j.get('datos')
            print(f"    estado={j.get('estado')} datos={datos}")
            if not datos:
                continue
            r2 = requests.get(datos, timeout=20, verify=verify)
            if not r2.encoding or r2.encoding.lower() == 'iso-8859-1':
                r2.encoding = 'ISO-8859-15'
            print(f"    paso2 status={r2.status_code} ct={r2.headers.get('Content-Type')} len={len(r2.content)}")
            print(f"    paso2 contenido[:400]={r2.text[:400]!r}")
            return  # éxito, no probar verify=False
        except Exception as e:
            print(f"    ERROR: {e.__class__.__name__}: {e}")


def main() -> None:
    a = Aemet()
    key = a.api_key or ''
    print(f"API key: {'OK' if key else 'VACÍA'} (prefijo {key[:12]}...)")
    print(f"Provincia: {a.province} -> código INE: {a.province_code()}")
    print(f"Ciudad: {a.city} -> código INE: {a.resolve_city_code()}")

    print("\n" + "=" * 64)
    print("SONDEO MANUAL — PROVINCIA")
    probe(f"{AEMET_OPENDATA_BASE}/prediccion/provincia/hoy/{a.province_code()}", key)

    print("\n" + "=" * 64)
    print("SONDEO MANUAL — MUNICIPIO")
    probe(f"{AEMET_OPENDATA_BASE}/prediccion/especifica/municipio/diaria/{a.resolve_city_code()}", key)

    print("\n" + "=" * 64)
    print("A TRAVÉS DEL MODELO Aemet (lo que usa el cron):")
    prov = a.fetch_province_forecast(day='hoy')
    if prov:
        print(f"  provincia (texto limpio) -> {len(prov)} chars: {prov[:300]}")
    else:
        print("  provincia -> None (API sin datos) => fallback a municipio")
    city = a.fetch_city_forecast()
    print(f"  municipio (fallback) -> {city if city else 'None'}")


if __name__ == "__main__":
    main()
