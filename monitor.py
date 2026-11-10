#!/usr/bin/env python3
"""Veille pluie / crue pour Safi et l'oued Chaaba.

Interroge Open-Meteo (plusieurs modeles meteo, plusieurs points du bassin),
calcule un niveau de vigilance et ecrit status.json + alert.md.
Bibliotheque standard uniquement.

Test hors ligne :  CHAABA_TEST_FILE=reponse.json python3 monitor.py
"""
import datetime as dt
import json
import os
import urllib.parse
import urllib.request

import nowcast

ROOT = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
    CFG = json.load(f)

WINDOWS = {"1h": 1, "3h": 3, "6h": 6, "24h": 24}
PAST_HOURS = 6
NAMES_FR = ["Vert", "Jaune", "Orange", "Rouge"]
NAMES_AR = ["أخضر", "أصفر", "برتقالي", "أحمر"]
MSG_FR = list(CFG["messages_fr"])
MSG_AR = list(CFG["messages_ar"])


def fetch():
    test = os.environ.get("CHAABA_TEST_FILE")
    if test:
        with open(test, encoding="utf-8") as f:
            data = json.load(f)
    else:
        pts = CFG["points"]
        q = {
            "latitude": ",".join(str(p["lat"]) for p in pts),
            "longitude": ",".join(str(p["lon"]) for p in pts),
            "hourly": "precipitation,wind_gusts_10m",
            "models": ",".join(CFG["models"]),
            "past_hours": PAST_HOURS,
            "forecast_hours": 48,
            "wind_speed_unit": "kmh",
            "timezone": "Africa/Casablanca",
        }
        url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q, safe=",")
        req = urllib.request.Request(url, headers={"User-Agent": "chaaba-veille"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    return data if isinstance(data, list) else [data]


def series_by_model(hourly, prefix):
    """{'modele': [valeurs]} pour une variable, que la reponse soit mono ou multi-modele."""
    out = {}
    for key, vals in hourly.items():
        if key == prefix or key.startswith(prefix + "_"):
            if not vals or all(v is None for v in vals):
                continue
            model = key[len(prefix):].lstrip("_") or "best_match"
            out[model] = [v or 0.0 for v in vals]
    return out


def rain_level(sums):
    th = CFG["rain_thresholds_mm"]
    for lvl in (3, 2, 1):
        if any(sums[w]["mm"] >= th[str(lvl)][w] for w in WINDOWS):
            return lvl
    return 0


def gust_level(g):
    th = CFG["gust_thresholds_kmh"]
    for lvl in (3, 2, 1):
        if g >= th[str(lvl)]:
            return lvl
    return 0


def analyse(data):
    worst = None          # pire couple (modele, point) pour la pluie
    model_levels = {}     # niveau max atteint par chaque modele
    gust = {"kmh": 0.0, "when": None, "model": None}
    offset = 0
    for i, loc in enumerate(data):
        hourly = loc["hourly"]
        times = hourly["time"]
        offset = loc.get("utc_offset_seconds", 0)
        point = CFG["points"][i]["name"] if i < len(CFG["points"]) else f"point {i}"
        for model, vals in series_by_model(hourly, "precipitation").items():
            sums = {}
            for w, n in WINDOWS.items():
                best, at = 0.0, 0
                for s in range(len(vals)):
                    tot = sum(vals[s:s + n])
                    if tot > best:
                        best, at = tot, s
                sums[w] = {"mm": round(best, 1), "start": times[at]}
            lvl = rain_level(sums)
            model_levels[model] = max(model_levels.get(model, 0), lvl)
            key = (lvl, sums["6h"]["mm"], sums["1h"]["mm"])
            if worst is None or key > worst["key"]:
                worst = {"key": key, "level": lvl, "model": model, "point": point, "sums": sums}
        for model, vals in series_by_model(hourly, "wind_gusts_10m").items():
            m = max(vals)
            if m > gust["kmh"]:
                gust = {"kmh": round(m), "when": times[vals.index(m)], "model": model}
    if worst is None:
        raise SystemExit("Aucune donnee de precipitation dans la reponse.")
    worst.pop("key")
    return worst, model_levels, gust, offset


def main():
    worst, model_levels, gust, offset = analyse(fetch())
    obs = nowcast.observe(CFG)   # ce que le satellite voit maintenant
    ol = obs.get("level", 0)
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_local = (now_utc + dt.timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M")

    rl, wl = worst["level"], gust_level(gust["kmh"])
    level = max(rl, ol)  # prevision OU observation satellite, le pire des deux
    #  le niveau affiche = risque de crue (pluie) ; le vent est donne a part
    n_models = len(model_levels)
    agree = sum(1 for v in model_levels.values() if v >= max(rl, 1))
    official = [o for o in CFG.get("official", []) if o["end"] >= now_local]

    msg_fr, msg_ar = MSG_FR[rl], MSG_AR[rl]
    if wl >= 1:  # le vent peut relever le niveau affiche : le dire clairement
        msg_fr += f" Vent : rafales jusqu'à {gust['kmh']} km/h selon le modèle le plus pessimiste."
        msg_ar += f" الرياح: هبات قد تصل إلى {gust['kmh']} كلم/س حسب أكثر النماذج تشاؤماً."
    if ol >= 1:  # l'observation en direct passe avant la prevision
        of, oa = CFG["obs_messages_fr"][ol], CFG["obs_messages_ar"][ol]
        msg_fr = of if ol > rl else of + " " + msg_fr
        msg_ar = oa if ol > rl else oa + " " + msg_ar
        obs["message_fr"], obs["message_ar"] = of, oa
    MSG_FR[rl], MSG_AR[rl] = msg_fr, msg_ar

    # --- Donnees publiques : mesures et previsions brutes, avec sources et heures, SANS niveau de danger ---
    # (aucun niveau public ne peut etre deduit automatiquement sans seuils approuves ni modele valide)
    obs_pub = {k: v for k, v in obs.items() if k not in ("level", "message_fr", "message_ar")}
    status = {
        "updated_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_local": now_local,
        "obs": obs_pub,
        "forecast": {
            "fetched_local": now_local,
            "max_1h": worst["sums"]["1h"], "max_3h": worst["sums"]["3h"],
            "max_6h": worst["sums"]["6h"], "max_24h": worst["sums"]["24h"],
            "model": worst["model"], "point": worst["point"], "models_total": n_models,
            "gust_max_kmh": gust["kmh"], "gust_when": gust["when"],
            "source": "Open-Meteo : prévision modélisée horaire, pas une mesure",
        },
        "official": official,
        "station_safi": {"wigos_id": "0-20000-0-60185", "status": "non connectée (point d'accès injoignable depuis le bot)"},
        "river_level": {"status": "aucun capteur installé"},
    }
    with open(os.path.join(ROOT, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    # --- Alerte PRIVEE pour le proprietaire seulement (jamais publiee) ---
    state_dir = os.path.join(ROOT, ".state")
    state_path = os.path.join(state_dir, "notify.json")
    prev = -1
    try:
        with open(state_path, encoding="utf-8") as f:
            prev = json.load(f).get("level", -1)
    except Exception:
        pass
    os.makedirs(state_dir, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"level": level, "utc": status["updated_utc"]}, f)

    s = worst["sums"]
    lines = [
        f"SAFI ALERT (prototype, privé) — indicateur interne {NAMES_FR[level]}",
        "",
        MSG_AR[rl], "",
        MSG_FR[rl], "",
        f"- Prévision (Open-Meteo, modèle {worst['model']}, {worst['point']}) : {s['1h']['mm']} mm en 1 h vers {s['1h']['start']}, "
        f"{s['6h']['mm']} mm en 6 h, {s['24h']['mm']} mm en 24 h ; accord des modèles {agree}/{n_models}",
        f"- Rafale max prévue : {gust['kmh']} km/h vers {gust['when']}",
        ("- Satellite (image pluie de %s UTC) : %s mm/h max sur 1 h, cumul estimé %s mm, éclairs sur le bassin : %s"
         % (obs.get("rain_image_utc"), obs.get("rate_max_1h_mmh"), obs.get("accum_1h_mm"), "OUI" if obs.get("lightning_basin") else "non"))
        if obs.get("ok") else "- Observation satellite indisponible : surveillance incomplète (pas synonyme de sécurité).",
        "",
        "Indicateur non validé, réservé au propriétaire. Ne pas diffuser comme alerte officielle.",
    ]
    alert = "\n".join(lines)
    notify = level >= 2 and level > prev
    if notify:
        topic = os.environ.get("NTFY_TOPIC")
        if topic:
            try:
                req = urllib.request.Request("https://ntfy.sh/" + urllib.parse.quote(topic), data=alert.encode("utf-8"),
                                             headers={"Title": "SAFI ALERT - indicateur " + NAMES_FR[level], "Priority": "5" if level == 3 else "4", "Tags": "warning"})
                urllib.request.urlopen(req, timeout=30)
            except Exception as e:
                print("ntfy :", e)
        tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if tok and chat:
            try:
                body = urllib.parse.urlencode({"chat_id": chat, "text": alert}).encode()
                urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", body, timeout=30)
            except Exception as e:  # ne jamais bloquer la veille pour une notification
                print("Telegram :", e)
    # le journal du bot est public : on n'y ecrit pas l'indicateur
    print("status.json mis a jour", status["updated_utc"], "| notification privee envoyee :", notify)


if __name__ == "__main__":
    main()
