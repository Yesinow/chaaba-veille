# Veille oued Chaâba — Safi

Bot GitHub qui surveille chaque heure la pluie prévue sur le bassin de l'oued Chaâba (Safi) et prévient en cas de risque.

- **Toutes les heures**, GitHub Actions lance `monitor.py`, qui interroge Open-Meteo (modèles ECMWF, GFS, ICON, Météo-France) sur 5 points du bassin.
- Il retient le **scénario le plus pessimiste** et le compare à des seuils calés sur la crue du 14/12/2025 (≈ 19 mm en 1 h, 35 mm en 6 h).
- Niveau orange ou rouge : une **issue** est ouverte (e-mail à tous ceux qui suivent le dépôt) et, en option, un message **Telegram** est envoyé.
- `index.html` est la page publique : quiconque l'ouvre pendant une alerte voit un écran « انتبه / Attention ».

## Installation (5 minutes)

1. Créez un dépôt GitHub **public** et envoyez-y tous ces fichiers (y compris le dossier `.github`).
2. *Settings → Actions → General → Workflow permissions* : cochez **Read and write permissions**.
3. *Settings → Pages* : source **Deploy from a branch**, branche `main`, dossier `/ (root)`. La page sera sur `https://VOTRE-NOM.github.io/NOM-DU-DEPOT/`.
4. *Actions → Veille oued Chaaba → Run workflow* pour le premier lancement.
5. Pour recevoir les alertes par e-mail : bouton **Watch → All activity** sur le dépôt.

### Telegram (facultatif)

Créez un bot avec @BotFather, puis ajoutez dans *Settings → Secrets and variables → Actions* les secrets `TELEGRAM_TOKEN` et `TELEGRAM_CHAT_ID` (identifiant d'un groupe ou d'un canal où le bot est admin).

## Réglages — `config.json`

- `points` : coordonnées **approximatives** du bassin. À affiner avec une carte du bassin versant.
- `rain_thresholds_mm` : seuils jaune (1), orange (2), rouge (3). Ils sont volontairement plus bas que la pluie observée en 2025, car les modèles sous-estiment les orages très localisés.
- `official` : bulletins de la DGM à afficher, saisis à la main (ils disparaissent seuls après leur heure de fin).

## Limites à connaître

- Ce n'est **pas** un système officiel et il ne mesure pas le niveau de l'eau dans l'oued : il n'y a pas de capteur. Il se fonde sur des prévisions.
- Les orages violents et très locaux sont mal prévus par tous les modèles : en décembre 2025, la prévision était d'environ 35 mm. Une alerte peut donc manquer, et de fausses alertes sont probables puisque le bot retient le pire scénario.
- Les images satellite sont proposées en liens directs (Zoom Earth, Windy, EUMETSAT) pour vérifier à l'œil ; elles n'entrent pas dans le calcul.
- GitHub peut retarder les tâches planifiées de quelques dizaines de minutes. La page signale les données de plus de 3 h comme périmées.

Données : [Open-Meteo](https://open-meteo.com/). Bulletins officiels : [DGM](https://vigilance.marocmeteo.ma/). Urgences : 15, 19, 177.
