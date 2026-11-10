# SAFI ALERT — prototype de suivi de l'oued Chaâba (Safi)

**Prototype, pas un service de l'État. Il ne publie aucune alerte.**

Page : https://yesinow.github.io/chaaba-veille/

## Ce que montre la page

- **Bandeau du haut** : uniquement les bulletins officiels de la DGM (saisis à la main dans `config.json` → `official`). Sans bulletin en cours, il l'affiche en clair et précise que cela ne veut pas dire « sans danger ».
- **Carte interactive** : tracé de l'oued (OpenStreetMap), vallée de la Chaâba, Bab Chaâba, images satellite animées (nuages, pluie estimée, éclairs, EUMETSAT/Meteosat) et bouton « où suis-je ? » qui donne la distance à l'oued.
- **Mesures satellite brutes** au-dessus du bassin, avec heure et source.
- **Prévisions Open-Meteo brutes** sur 48 h : il s'agit d'une prévision modélisée, pas d'une mesure.
- **Station officielle SAFI (WIGOS 0-20000-0-60185)** et **niveau de l'oued** : affichés « non disponible » tant qu'aucune donnée réelle n'est reçue.

## Règles

1. Ne jamais inventer de niveau d'eau, de mesure ou de prévision.
2. Toujours afficher la source et l'heure.
3. Aucun niveau de danger public déduit automatiquement sans seuils approuvés et modèle validé.
4. Donnée manquante = surveillance indisponible, jamais « sans danger ».
5. Aucune alerte publiée par le prototype.

## Notification privée (pour le propriétaire seulement)

Le bot (`monitor.py`, lancé par GitHub Actions toutes les 10 min au mieux) calcule un indicateur interne non validé. Il ne le publie nulle part, mais peut vous l'envoyer **à vous seul** :

- **ntfy** : installez l'application ntfy, abonnez-vous à un nom de sujet long et secret, puis ajoutez ce nom dans *Settings → Secrets and variables → Actions* sous `NTFY_TOPIC`.
- ou **Telegram** : secrets `TELEGRAM_TOKEN` et `TELEGRAM_CHAT_ID`.

## Limites

- Aucun capteur de niveau d'eau ni pluviomètre dans l'oued.
- La station SAFI de la DGM n'est pas joignable depuis GitHub pour l'instant.
- Le satellite estime la pluie avec 15 à 50 min de retard.
- GitHub retarde souvent les lancements planifiés.

Données : Open-Meteo, EUMETSAT (EUMETView), © OpenStreetMap, imagerie Esri, bulletins DGM. Urgences : 15, 19, 177.
