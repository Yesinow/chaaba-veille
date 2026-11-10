"""Sonde : trace de l'oued Chaaba dans OpenStreetMap + compatibilite carte des couches EUMETView."""
import json
import urllib.parse
import urllib.request

UA = {"User-Agent": "chaaba-veille (github.com/Yesinow/chaaba-veille)"}


def http(url, data=None, headers=None, timeout=120):
    h = dict(UA)
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, dict(r.headers), r.read()


# 1) Cours d'eau autour de Safi dans OpenStreetMap
q = """[out:json][timeout:90];
(
  way["waterway"](32.20,-9.32,32.50,-9.00);
  relation["waterway"](32.20,-9.32,32.50,-9.00);
  way["natural"="water"](32.20,-9.32,32.50,-9.00);
  way["name"~"[Cc]ha[aâ]?ba|شعبة|Haroun|هارون"](32.10,-9.40,32.60,-8.90);
);
out tags geom;"""
for ep in ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"):
    try:
        st, hd, body = http(ep, data=urllib.parse.urlencode({"data": q}).encode())
        d = json.loads(body)
        print("overpass", ep, st, len(d.get("elements", [])), "elements")
        out = []
        for el in d["elements"]:
            t = el.get("tags", {})
            geom = el.get("geometry") or []
            n = len(geom)
            first = geom[0] if geom else {}
            last = geom[-1] if geom else {}
            print(f'{el["type"]} {el["id"]} {t.get("waterway") or t.get("natural")} name={t.get("name")!r} '
                  f'name:ar={t.get("name:ar")!r} name:fr={t.get("name:fr")!r} pts={n} '
                  f'de=({first.get("lat")},{first.get("lon")}) a=({last.get("lat")},{last.get("lon")})')
            out.append(el)
        json.dump(out, open("osm_eau.json", "w"))
        break
    except Exception as e:
        print("overpass echec", ep, e)

# 2) EUMETView : CORS et projection web (EPSG:3857) pour une carte interactive
W = "https://view.eumetsat.int/geoserver/wms"
p = {"service": "WMS", "version": "1.3.0", "request": "GetMap", "layers": "mtg_fd:ir105_hrfi", "styles": "",
     "crs": "EPSG:3857", "bbox": "-1113194,3757032,-890555,3913575", "width": 256, "height": 256,
     "format": "image/png", "transparent": "true"}
try:
    st, hd, body = http(W + "?" + urllib.parse.urlencode(p), headers={"Origin": "https://yesinow.github.io"})
    print("GetMap 3857", st, hd.get("Content-Type"), len(body), "CORS:", hd.get("Access-Control-Allow-Origin"))
except Exception as e:
    print("GetMap 3857 echec", e)
p2 = {"service": "WMS", "version": "1.3.0", "request": "GetFeatureInfo", "layers": "mtg_fd:h40b",
      "query_layers": "mtg_fd:h40b", "styles": "", "crs": "EPSG:4326", "bbox": "32.28,-9.26,32.32,-9.22",
      "width": 3, "height": 3, "i": 1, "j": 1, "info_format": "application/json"}
try:
    st, hd, body = http(W + "?" + urllib.parse.urlencode(p2), headers={"Origin": "https://yesinow.github.io"})
    print("GFI", st, "CORS:", hd.get("Access-Control-Allow-Origin"), body[:200])
except Exception as e:
    print("GFI echec", e)
