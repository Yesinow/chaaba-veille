"""Sonde : la station officielle SAFI (WIGOS 0-20000-0-60185) sur wis2box de la DGM."""
import json, urllib.request, urllib.parse
B = "https://wis2box.marocmeteo.ma/oapi"
def get(u):
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "chaaba-veille", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, r.headers.get("Access-Control-Allow-Origin"), json.load(r)
    except Exception as e:
        return "ERR", None, str(e)[:300]
st, cors, d = get(B + "/collections/stations/items/0-20000-0-60185?f=json")
print("station", st, "CORS", cors); print(json.dumps(d, ensure_ascii=False)[:1500])
st, cors, d = get(B + "/collections?f=json")
print("collections", st)
if isinstance(d, dict):
    for c in d.get("collections", []): print(" ", c.get("id"), "|", c.get("title"), "|", (c.get("extent") or {}).get("temporal"))
C = B + "/collections/" + urllib.parse.quote("urn:wmo:md:ma-marocmeteo:h6vqw6", safe="")
for q in ("/items?f=json&limit=3", "/items?f=json&wigos_station_identifier=0-20000-0-60185&limit=200&sortby=-resultTime",
          "/items?f=json&wigos_station_identifier=0-20000-0-60185&limit=200&sortby=-reportTime"):
    st, cors, d = get(C + q)
    print("==", q, st, "CORS", cors)
    if isinstance(d, dict):
        fs = d.get("features", [])
        print(" numberMatched", d.get("numberMatched"), "returned", len(fs))
        names = {}
        for f in fs:
            p = f.get("properties", {})
            k = p.get("name"); names.setdefault(k, []).append((p.get("resultTime") or p.get("phenomenonTime") or p.get("reportTime"), p.get("value"), p.get("units")))
        for k, v in list(names.items())[:40]: print("  ", k, v[:2])
        if fs: print("  exemple:", json.dumps(fs[0], ensure_ascii=False)[:900])
    else:
        print(" ", d)
