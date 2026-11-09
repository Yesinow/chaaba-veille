"""Sonde : que renvoie EUMETView (satellite Meteosat) au-dessus du bassin de l'oued Chaaba ?"""
import re
import urllib.parse
import urllib.request

WMS = "https://view.eumetsat.int/geoserver/wms"
LAYERS = ["mtg_fd:h40b", "msg_fes:h60b", "mtg_fd:li_afa", "msg_fes:rdt", "mtg_fd:ir105_hrfi"]


def get(params, n=1500):
    url = WMS + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "chaaba-veille"}), timeout=90) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except Exception as e:
        return "ERR", str(e), b""


st, ct, caps = get({"service": "WMS", "version": "1.3.0", "request": "GetCapabilities"})
caps = caps.decode("utf-8", "replace")
for lay in LAYERS:
    print("=====", lay)
    m = re.search(r"<Layer[^>]*>\s*<Name>" + re.escape(lay) + r"</Name>(.*?)</Layer>", caps, re.S)
    block = m.group(1) if m else ""
    t = re.search(r"<Title>(.*?)</Title>", block, re.S)
    a = re.search(r"<Abstract>(.*?)</Abstract>", block, re.S)
    d = re.search(r'<Dimension name="time"([^>]*)>(.*?)</Dimension>', block, re.S)
    print("titre:", t.group(1).strip() if t else None)
    print("resume:", (a.group(1).strip()[:500] if a else None))
    if d:
        ext = d.group(2).strip()
        print("time attrs:", d.group(1).strip(), "| extent:", ext[:80], "...", ext[-80:])
    print("styles:", re.findall(r"<Style>\s*<Name>(.*?)</Name>", block)[:6])
    # bassin : lat 32.20..32.40, lon -9.34..-9.10 ; WMS 1.3.0 EPSG:4326 => ordre lat,lon
    base = {"service": "WMS", "version": "1.3.0", "layers": lay, "styles": "", "crs": "EPSG:4326",
            "bbox": "32.20,-9.34,32.40,-9.10", "width": 24, "height": 20}
    for fmt in ("application/json", "text/plain"):
        p = dict(base, request="GetFeatureInfo", query_layers=lay, info_format=fmt, i=12, j=10, feature_count=5)
        st, ct, body = get(p)
        print("GFI", fmt, st, ct, body[:700].decode("utf-8", "replace").replace("\n", " "))
    st, ct, body = get(dict(base, request="GetMap", format="image/png", transparent="true"))
    print("GetMap", st, ct, len(body), "octets")
    lg = re.search(r'<LegendURL[^>]*>.*?xlink:href="([^"]+)"', block, re.S)
    print("legende:", lg.group(1).replace("&amp;", "&") if lg else None)
