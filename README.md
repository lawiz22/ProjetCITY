# Central City Scrutinizer (CCS)

Urban Intelligence Analytic Platform — plateforme locale d'analyse urbaine pour villes canadiennes et américaines.

310+ villes | 13 provinces/territoires | 51 états | Base SQLite en étoile | Flask + Chart.js + Leaflet | IA générative Mammouth | 66 drapeaux

---

## Démarrage rapide

Sous Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\build_city_database.py   # première fois seulement
python run_web.py
# → http://127.0.0.1:5000
```

---

## Pages principales

### Dashboard (`/`)
- Indicateurs clés : nombre de villes (avec drapeaux 🇨🇦🇺🇸), couverture temporelle, croissance moyenne
- Palmarès croissance / déclin, pics historiques
- Export PDF du dashboard complet

### Annuaire des villes (`/cities`)
- Double affichage : vue blocs illustrée (large, medium, small) et vue liste compacte
- Filtres dynamiques par pays, région, population
- Population récente, pic historique et photo HD pour chaque ville

### Fiche détaillée (`/cities/<slug>`)
- Header photo premium avec badges de synthèse et résumé narratif
- Courbe démographique interactive avec annotations (bandes verticales colorées, filtres à cocher)
- Timeline visuelle des périodes détaillées avec surbrillance croisée
- Mode lecture guidée période par période (autoplay, barre flottante)
- Navigation rapide par ancres (Courbe, Annotations, Timeline, Export)
- Galerie photo avec badges EXIF (GPS, date, appareil), lightbox plein écran
- Photos d'annotation avec recherche web intelligente et traduction anglaise automatique
- Bouton « Voir sur la carte » pour localiser la ville directement sur la carte interactive
- Export PDF enrichi avec photo et badges
- Export PNG des graphiques

### Comparaison multi-villes (`/compare`)
- Sélection multiple de villes avec tableau comparatif
- Courbes superposées avec zoom, pan et réinitialisation

### Carte interactive (`/map`)
- Bulles proportionnelles à la population récente
- 7 fonds de carte : CARTO Voyager, Positron, Dark Matter, OpenStreetMap, Esri Satellite, Esri Topo, OpenTopoMap
- Couches thématiques : population, croissance, déclin, pics, annotations, climat, densité
- Filtres dynamiques (pays, région, population, recherche texte)
- Sauvegarde de la vue par défaut (zoom, position, fond de carte, couche) via localStorage
- Focus automatique sur une ville via paramètre URL `?focus=<slug>`
- **Voyage dans le temps** : slider temporel avec lecture automatique (lent/normal/rapide)
  - Bloc « Villes affichées » : tableau trié par population avec densité calculée dynamiquement
  - Bloc « Chroniques des villes » : périodes historiques actives par ville, mises à jour en temps réel
  - Entrée directe via URL `?tt=1&year=YEAR&country=COUNTRY&region=REGION` avec zoom automatique

### SQL Lab (`/sql-lab`)
- Requêtes SQL directes sur la base SQLite (lecture par défaut)
- Snippets d'exemples, historique persistant (60 entrées), vues sauvegardées (80 max)
- Export CSV des résultats
- Mode écriture optionnel via `PROJETCITY_SQL_ENABLE_WRITE=1`

### AI Lab (`/ai-lab`)
- Génération de fiches ville complètes via API Mammouth AI en 3 étapes
- Bouton « Générer les 3 étapes » avec retry automatique
- Bouton « Suggérer une ville » intelligent avec filtres pays/région et priorité aux régions manquantes
- Comparaison et fusion sélective avec les données existantes (population, annotations, périodes, fiche)
- Import direct dans la base avec géocodage et photo automatiques

### Géo-couverture (`/geo-coverage`)
- Couverture géographique par province canadienne et état américain
- Base de 630 villes de référence (130 CA + 500 US) avec barres de progression par région
- Tableau des villes de référence manquantes avec bouton « Générer » vers l'AI Lab
- Bouton « Ajouter 20 villes » par région pour enrichir la base de référence via IA (prompts progressifs)
- Onglets Canada / États-Unis avec recherche par région

### Population de référence (`/reference-population`)
- Couverture nationale et régionale (pop. de référence vs pop. dans la BD)
- Filtres par pays, région/état, années (multi-select)
- Drapeaux pour chaque pays et région/état (66 drapeaux : 2 pays + 13 provinces CA + 51 états US)
- Bouton 🗺️ lien direct vers la carte en mode voyage dans le temps
- Barres de progression colorées (vert/orange/rouge)

### Couverture des données (`/coverage`)
- Villes sans fiche complète, sans photos, sans périodes détaillées
- Décennies manquantes par ville
- Export CSV de la couverture et des décennies manquantes

### Options (`/options`)
- Configuration API Mammouth AI (clé, modèle, test de connexion)
- Suivi des tokens utilisés

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Flask (Python) |
| Base de données | SQLite3 (schéma en étoile) |
| Templates | Jinja2 |
| Graphiques | Chart.js |
| Carte | Leaflet.js 1.9.4 |
| PDF | ReportLab |
| Images | Pillow, Wikipedia / Wikimedia Commons (1280px HD) |
| Analytics | Matplotlib, NumPy, Pandas |
| IA | API Mammouth AI (compatible OpenAI) |

---

## Structure du projet

```
run_web.py                          → point d'entrée Flask
app/
  __init__.py                       → factory Flask
  config.py                         → configuration (env vars)
  db.py                             → connexion SQLite
  routes.py                         → toutes les routes web + API
  services/
    analytics.py                    → métriques, dashboard, exécution SQL
    city_coordinates.py             → géocodage (cache + fallback web)
    city_import.py                  → import population, périodes, fiches, photos
    city_photos.py                  → recherche Wikipedia/Commons, galerie, EXIF
    mammouth_ai.py                  → client API Mammouth AI, tokens
    pdf_reports.py                  → génération PDF (dashboard, fiche ville)
sql/
  schema.sql                        → schéma complet (tables, vues, index)
scripts/
  build_city_database.py            → construction initiale de la base
  build_ref_cities.py               → base de 630 villes de référence via IA
  fetch_city_photos.py              → téléchargement batch des photos Wikipedia
  import_city_period_details.py     → rechargement des périodes depuis les .txt
  import_reference_population.py    → import données de population de référence
  repair_city_dimension.py          → correction de base existante
  validate_villestats.py            → validation villestats.py
  validate_villestats_v2.py         → validation villestats_v2.py
  validate_city_period_details.py   → validation des fichiers .txt
data/
  city_analysis.db                  → base SQLite générée
  city_details/                     → 65+ fichiers .txt de périodes détaillées
  ref_cities.json                   → villes de référence (630 entrées)
  saved_views.json                  → vues SQL sauvegardées
  sql_lab_history.json              → historique SQL Lab
templates/web/                      → 14 templates Jinja2
static/
  css/app.css, leaflet.css          → styles de la plateforme
  js/charts.js, leaflet.js,         → modules JS (graphiques, carte,
     map.js, map_static.js,            SQL Lab, tables, thème)
     sql_lab.js, tables.js, ui.js
  images/cities/                    → photos HD par ville
  images/flags/                     → drapeaux (66 : pays + provinces/états)
villestats.py                       → données source (séries historiques)
villestats_v2.py                    → données source (format simplifié)
```

---

## Modèle de données (schéma en étoile)

### Tables

| Table | Rôle |
|-------|------|
| `fact_city_population` | Table de faits : ville, année, population, annotation |
| `dim_city` | Dimension ville : nom, slug, région, pays, coordonnées, superficie, densité, couleur |
| `dim_time` | Dimension temps : année, décennie, quart/demi-siècle, siècle, période historique |
| `dim_annotation` | Dimension annotation : label, couleur, type, photo |
| `dim_city_period_detail` | Périodes narratives par ville (titre, dates, texte consolidé) |
| `dim_city_period_detail_item` | Points de détail par période |
| `dim_city_fiche` | Fiche complète par ville (texte brut + sections parsées) |
| `dim_city_fiche_section` | Sections de fiche (emoji, titre, contenu JSON) |
| `dim_city_photo` | Bibliothèque photo (fichier, légende, EXIF, attribution) |
| `ref_city` | Villes de référence par région (630 villes, 63 régions) |
| `ref_population` | Population de référence par région/année |

### Vues analytiques

| Vue | Description |
|-----|-------------|
| `vw_city_population_analysis` | Vue complète avec ville + temps + annotations |
| `vw_city_growth_by_decade` | Croissance absolue et relative par décennie |
| `vw_city_peak_population` | Pic démographique par ville |
| `vw_city_decline_periods` | Périodes de déclin entre observations |
| `vw_city_rebound_periods` | Périodes de reprise après stagnation/recul |
| `vw_annotated_events_by_period` | Événements annotés avec contexte temporel |
| `vw_city_period_detail_analysis` | Lecture analytique des périodes détaillées |
| `vw_city_period_detail_with_population` | Périodes avec population début/fin et variation |
| `vw_city_period_detail_with_annotations` | Périodes avec annotations couvertes |

---

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `PROJETCITY_DATABASE_PATH` | `data/city_analysis.db` | Chemin vers la base SQLite |
| `PROJETCITY_SQL_QUERY_LIMIT` | `500` | Lignes max par requête SQL Lab |
| `PROJETCITY_SQL_EXPORT_LIMIT` | `5000` | Lignes max en export CSV |
| `PROJETCITY_SQL_HISTORY_PATH` | `data/sql_lab_history.json` | Fichier historique SQL |
| `PROJETCITY_SQL_HISTORY_LIMIT` | `60` | Entrées max dans l'historique |
| `PROJETCITY_SAVED_VIEWS_PATH` | `data/saved_views.json` | Fichier vues sauvegardées |
| `PROJETCITY_SAVED_VIEWS_LIMIT` | `80` | Vues max sauvegardées |
| `PROJETCITY_SQL_STATEMENT_LIMIT` | — | Instructions max par exécution |
| `PROJETCITY_SQL_ENABLE_WRITE` | `0` | `1` pour activer les requêtes en écriture |

---

## Scripts utilitaires

```powershell
# Recharger la base complète
python scripts\build_city_database.py

# Recharger seulement les périodes détaillées
python scripts\import_city_period_details.py

# Valider les fichiers source
python scripts\validate_villestats.py
python scripts\validate_villestats_v2.py
python scripts\validate_city_period_details.py

# Corriger une base existante (ancien schéma)
python scripts\repair_city_dimension.py

# Télécharger les photos Wikipedia
python scripts\fetch_city_photos.py

# Télécharger les drapeaux (flagcdn.com + Wikimedia)
python scripts\download_flags.py
```

---

## Exemples de requêtes SQL

```sql
SELECT city_name, year, population, period_label, annotation_label
FROM vw_city_population_analysis
WHERE country = 'Canada'
ORDER BY city_name, year;
```

```sql
SELECT city_name, decade, absolute_growth, growth_pct
FROM vw_city_growth_by_decade
ORDER BY growth_pct DESC
LIMIT 10;
```

```sql
SELECT city_name, peak_year, peak_population
FROM vw_city_peak_population
ORDER BY peak_population DESC;
```

---

## Idées pour la suite

- migrations interurbaines
- déplacements domicile-travail
- immobilier / loyers / prix
- emploi et revenus
- transport collectif
- émissions et usage du sol
- événements historiques majeurs
