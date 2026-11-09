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

ROOT = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
    CFG = json.load(f)

WINDOWS = {"1h": 1, "3h": 3, "6h": 6, "24h": 24}
PAST_HOURS = 6
NAMES_FR = ["Vert", "Jaune", "Orange", "Rouge"]
NAMES_AR = ["أخضر", "أصفر", "برتقالي", "أحمر"]
MSG_FR = [
    "Pas de pluie dangereuse prévue sur le bassin de l'oued Chaâba dans les 48 h.",
    "Pluie notable prévue. Restez informé et surveillez les bulletins officiels.",
    "Fortes pluies possibles : risque de montée rapide de l'oued Chaâba. Éloignez-vous du lit de l'oued, de Bab Chaâba et des points bas. Mettez véhicules et marchandises à l'abri.",
    "DANGER : pluies du niveau de la crue du 14/12/2025. Ne restez pas près de l'oued Chaâba ni dans les rez-de-chaussée des zones basses. Montez en hauteur. Ne traversez jamais une rue inondée.",
]
MSG_AR = [
    "لا توجد أمطار خطيرة متوقعة على حوض واد الشعبة خلال 48 ساعة القادمة.",
    "أمطار مهمة متوقعة. ابقَ على اطلاع وتابع النشرات الرسمية.",
    "أمطار قوية محتملة: خطر ارتفاع سريع لمنسوب واد الشعبة. ابتعد عن مجرى الواد وباب الشعبة والمناطق المنخفضة. ضع السيارات والسلع في مكان آمن.",
    "خطر: أمطار في مستوى فيضان 14 دجنبر 2025. لا تبقَ قرب واد الشعبة ولا في الطوابق الأرضية بالمناطق المنخفضة. اصعد إلى مكان مرتفع. لا تعبر أبداً شارعاً مغموراً بالمياه.",
]


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
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_local = (now_utc + dt.timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M")

    rl, wl = worst["level"], gust_level(gust["kmh"])
    level = max(rl, wl)
    n_models = len(model_levels)
    agree = sum(1 for v in model_levels.values() if v >= max(rl, 1))
    official = [o for o in CFG.get("official", []) if o["end"] >= now_local]

    msg_fr, msg_ar = MSG_FR[rl], MSG_AR[rl]
    if wl >= 1:  # le vent peut relever le niveau affiche : le dire clairement
        msg_fr += f" Vent : rafales jusqu'à {gust['kmh']} km/h prévues."
        msg_ar += f" الرياح: هبات متوقعة تصل إلى {gust['kmh']} كلم/س."
    MSG_FR[rl], MSG_AR[rl] = msg_fr, msg_ar

    status_path = os.path.join(ROOT, "status.json")
    prev = -1
    if os.path.exists(status_path):
        try:
            with open(status_path, encoding="utf-8") as f:
                prev = json.load(f).get("level", -1)
        except Exception:
            pass

    status = {
        "updated_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_local": now_local,
        "level": level,
        "level_fr": NAMES_FR[level],
        "level_ar": NAMES_AR[level],
        "message_fr": MSG_FR[rl],
        "message_ar": MSG_AR[rl],
        "rain": {
            "level": rl,
            "worst_model": worst["model"],
            "worst_point": worst["point"],
            "sums": worst["sums"],
            "models_agree": agree,
            "models_total": n_models,
            "model_levels": model_levels,
        },
        "wind": {"level": wl, **gust},
        "official": official,
        "source": "Open-Meteo (ECMWF, GFS, ICON, Meteo-France). Indicatif, non officiel.",
    }
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    s = worst["sums"]
    lines = [
        f"## Vigilance {NAMES_FR[level]} / {NAMES_AR[level]} — Safi, oued Chaâba",
        "",
        MSG_AR[rl], "",
        MSG_FR[rl], "",
        f"- Pluie max prévue : **{s['1h']['mm']} mm en 1 h** (vers {s['1h']['start']}), "
        f"**{s['6h']['mm']} mm en 6 h** (à partir de {s['6h']['start']}), {s['24h']['mm']} mm en 24 h",
        f"- Scénario le plus pessimiste : modèle `{worst['model']}`, point « {worst['point']} »",
        f"- Accord des modèles : {agree}/{n_models}" + (" (confiance faible)" if agree <= 1 and n_models > 1 else ""),
        f"- Rafale max prévue : {gust['kmh']} km/h (vers {gust['when']})",
        "- Repère : le 14/12/2025, Safi a reçu environ 19 mm en 1 h et 35 mm en 6 h.",
        "",
        "Heures locales. Estimation automatique à partir de modèles météo, **non officielle**. "
        "Suivez la DGM (vigilance.marocmeteo.ma) et les autorités. Urgences : 15 (Protection civile), 19 (police), 177 (gendarmerie).",
    ]
    alert = "\n".join(lines)
    with open(os.path.join(ROOT, "alert.md"), "w", encoding="utf-8") as f:
        f.write(alert + "\n")

    notify = level >= 2 and level > prev
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"notify={'true' if notify else 'false'}\n")
            f.write(f"title=Vigilance {NAMES_FR[level]} - Safi / oued Chaaba - {now_local}\n")

    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if notify and tok and chat:
        body = urllib.parse.urlencode({"chat_id": chat, "text": alert.replace("**", "").replace("## ", "")}).encode()
        try:
            urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", body, timeout=30)
        except Exception as e:  # ne jamais bloquer la veille pour une notification
            print("Telegram :", e)

    print(alert)
    print(f"\nniveau={level} precedent={prev} notifier={notify}")


if __name__ == "__main__":
    main()
