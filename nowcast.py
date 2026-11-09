"""Observation en temps quasi reel par satellite (Meteosat MTG, via EUMETView / EUMETSAT).

Contrairement aux previsions, ceci regarde ce qui se passe VRAIMENT au-dessus du bassin :
  - mtg_fd:h40b   : intensite de pluie estimee par satellite (mm/h), image toutes les 10 min
  - mtg_fd:li_afa : eclairs detectes par le Lightning Imager, image toutes les 5 min
Limites : estimation satellite (pas un pluviometre), disponible avec 15 a 50 min de retard.
"""
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import struct
import urllib.parse
import urllib.request
import zlib

WMS = "https://view.eumetsat.int/geoserver/wms"
RAIN, LIGHT = "mtg_fd:h40b", "mtg_fd:li_afa"
# Boites (sud, ouest, nord, est)
NEAR = (31.80, -9.80, 32.80, -8.60)    # ~110 km autour de Safi : orages qui approchent
BASIN = (32.20, -9.32, 32.42, -9.06)   # bassin de l'oued Chaaba (approximatif)
W, H = 60, 50


def _get(params, timeout=60):
    url = WMS + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "chaaba-veille"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _png_alpha(data):
    """Decodeur PNG minimal (8 bits, non entrelace) -> lignes de booleens 'pixel colore'."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("pas un PNG")
    pos, idat, plte, trns = 8, b"", None, None
    while pos < len(data):
        n, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"tRNS":
            trns = body
        elif typ == b"IDAT":
            idat += body
        pos += 12 + n
    if depth != 8 or interlace:
        raise ValueError("format PNG non gere")
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw, stride = zlib.decompress(idat), w * ch
    rows, prev, p = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        for i in range(stride):
            a = line[i - ch] if i >= ch else 0
            b = prev[i]
            c = prev[i - ch] if i >= ch else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        out = []
        for x in range(w):
            px = line[x * ch:(x + 1) * ch]
            if ctype == 6:
                on = px[3] > 0 and (px[0] or px[1] or px[2])
            elif ctype == 4:
                on = px[1] > 0 and px[0] > 0
            elif ctype == 3:
                alpha = trns[px[0]] if trns is not None and px[0] < len(trns) else 255
                rgb = plte[px[0] * 3:px[0] * 3 + 3] if plte else b"\x01"
                on = alpha > 0 and any(rgb)
            else:
                on = any(px)
            out.append(bool(on))
        rows.append(out)
    return rows


def _count(layer, time):
    """Nombre de pixels colores (pluie / eclairs) pres de Safi et sur le bassin."""
    s, w, n, e = NEAR
    png = _get({"service": "WMS", "version": "1.3.0", "request": "GetMap", "layers": layer, "styles": "",
                "crs": "EPSG:4326", "bbox": f"{s},{w},{n},{e}", "width": W, "height": H,
                "format": "image/png", "transparent": "true", "time": time})
    near = basin = 0
    for y, row in enumerate(_png_alpha(png)):
        lat = n - (y + 0.5) / H * (n - s)
        for x, on in enumerate(row):
            if on:
                lon = w + (x + 0.5) / W * (e - w)
                near += 1
                if BASIN[0] <= lat <= BASIN[2] and BASIN[1] <= lon <= BASIN[3]:
                    basin += 1
    return near, basin


def _rate(lat, lon, time):
    """Intensite de pluie satellite (mm/h) en un point."""
    d = 0.02
    raw = _get({"service": "WMS", "version": "1.3.0", "request": "GetFeatureInfo", "layers": RAIN,
                "query_layers": RAIN, "styles": "", "crs": "EPSG:4326",
                "bbox": f"{lat - d},{lon - d},{lat + d},{lon + d}", "width": 3, "height": 3, "i": 1, "j": 1,
                "info_format": "application/json", "time": time})
    feats = json.loads(raw).get("features") or []
    if not feats:
        return 0.0
    v = feats[0]["properties"].get("Instantaneous_rain_rate")
    return float(v) if v is not None and 0 <= float(v) < 500 else 0.0


def _latest(caps, layer):
    m = re.search(r"<Name>" + re.escape(layer) + r"</Name>.*?<Dimension name=\"time\" default=\"([^\"]+)\"", caps, re.S)
    return dt.datetime.strptime(m.group(1)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def observe(cfg):
    if os.environ.get("CHAABA_TEST_FILE"):
        f = os.environ.get("CHAABA_TEST_OBS")
        if f:
            with open(f, encoding="utf-8") as fh:
                return json.load(fh)
        return {"ok": False, "level": 0}
    try:
        return _observe(cfg)
    except Exception as e:  # la veille ne doit jamais tomber a cause du satellite
        print("Observation satellite indisponible :", e)
        return {"ok": False, "level": 0, "error": str(e)[:200]}


def _observe(cfg):
    th = cfg["obs_thresholds"]
    now = dt.datetime.now(dt.timezone.utc)
    caps = _get({"service": "WMS", "version": "1.3.0", "request": "GetCapabilities"}, 120).decode("utf-8", "replace")
    t_rain, t_light = _latest(caps, RAIN), _latest(caps, LIGHT)
    rain_times = [t_rain - dt.timedelta(minutes=10 * k) for k in range(6)]    # derniere heure
    light_times = [t_light - dt.timedelta(minutes=5 * k) for k in range(6)]   # 30 dernieres minutes
    pts = cfg["points"]

    jobs = {}
    with cf.ThreadPoolExecutor(8) as ex:
        for t in light_times:
            jobs[ex.submit(_count, LIGHT, _iso(t))] = ("light", t)
        jobs[ex.submit(_count, RAIN, _iso(t_rain))] = ("rainmap", t_rain)
        for i, p in enumerate(pts):
            for t in rain_times:
                jobs[ex.submit(_rate, p["lat"], p["lon"], _iso(t))] = ("rate", i, t)
        light_near = light_basin = rain_near = rain_basin = failed = 0
        rates = {}
        for fut in cf.as_completed(jobs):
            key = jobs[fut]
            try:
                res = fut.result()
            except Exception as e:
                failed += 1
                print("requete satellite echouee :", key[0], str(e)[:80])
                continue
            if key[0] == "light":
                light_near += res[0]
                light_basin += res[1]
            elif key[0] == "rainmap":
                rain_near, rain_basin = res
            else:
                rates[(key[1], key[2])] = res
    if failed > len(jobs) / 2:
        raise RuntimeError(f"{failed}/{len(jobs)} requetes satellite en echec")

    rate_now = max((rates.get((i, rain_times[0]), 0.0) for i in range(len(pts))), default=0.0)
    rate_max, accum, where = 0.0, 0.0, None
    for i, p in enumerate(pts):
        vals = [rates.get((i, t), 0.0) for t in rain_times]
        a = sum(vals) / 6.0   # 6 images de 10 min -> mm sur 1 h
        if max(vals) > rate_max:
            rate_max = max(vals)
        if a > accum or where is None:
            accum, where = max(a, accum), p["name"] if a >= accum else where

    level = 0
    if rate_max >= th["rate_yellow"] or light_near or rain_near:
        level = 1
    if rate_max >= th["rate_orange"] or accum >= th["accum_orange"] or light_basin:
        level = 2
    if accum >= th["accum_red"] or rate_max >= th["rate_red"] or (light_basin and rate_max >= th["rate_orange"]):
        level = 3

    return {
        "ok": True,
        "level": level,
        "rate_now_mmh": round(rate_now, 1),
        "rate_max_1h_mmh": round(rate_max, 1),
        "accum_1h_mm": round(accum, 1),
        "worst_point": where,
        "lightning_basin": bool(light_basin),
        "lightning_near": bool(light_near),
        "rain_near": bool(rain_near),
        "rain_image_utc": t_rain.strftime("%Y-%m-%dT%H:%MZ"),
        "lightning_image_utc": t_light.strftime("%Y-%m-%dT%H:%MZ"),
        "rain_age_min": int((now - t_rain).total_seconds() // 60),
        "lightning_age_min": int((now - t_light).total_seconds() // 60),
        "failed_requests": failed,
        "source": "EUMETSAT Meteosat MTG (H SAF H40B, Lightning Imager) via EUMETView",
    }


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "config.json"), encoding="utf-8") as fh:
        print(json.dumps(observe(json.load(fh)), ensure_ascii=False, indent=2))
