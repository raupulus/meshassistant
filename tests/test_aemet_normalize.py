import unicodedata
def _normalize_name(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', s)
    s2 = ''.join([c for c in nfkd if not unicodedata.combining(c)])
    return ' '.join(s2.split()).upper()

prov_raw = "Cádiz"
prov_norm = _normalize_name(prov_raw)
prov_title = prov_raw.title()
print([prov_norm, prov_title, prov_raw])
print(prov_norm.title())
