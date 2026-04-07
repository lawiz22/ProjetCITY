# Central City Scrutinizer

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![PostGIS](https://img.shields.io/badge/PostGIS-3.4-5CAE58)
![Leaflet](https://img.shields.io/badge/Leaflet-1.9-199900?logo=leaflet&logoColor=white)
![Chart.js](https://img.shields.io/badge/Chart.js-4.x-FF6384?logo=chartdotjs&logoColor=white)
![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?logo=railway&logoColor=white)
![License](https://img.shields.io/badge/License-Private-red)

**Urban Intelligence Platform** — analyse démographique, cartographique et historique de 310+ villes nord-américaines, avec IA générative intégrée.

---

## Fonctionnalités

| Module | Description |
|--------|-------------|
| **Dashboard** | KPIs, palmarès croissance/déclin, pics historiques, export PDF |
| **Annuaire** | Vues blocs/liste, filtres pays/région/population, photos HD |
| **Fiches ville** | Courbe interactive, annotations, timeline, périodes narratives, galerie photo, export PDF/PNG |
| **Carte** | Bulles proportionnelles, 7 fonds de carte, couches thématiques, voyage dans le temps |
| **Comparaison** | Courbes multi-villes superposées avec zoom/pan |
| **Événements** | Catalogue historique (10 catégories, 2 niveaux), fiches détaillées, galerie photo |
| **Pays & Régions** | Fiches détaillées avec populations, annotations, périodes, galerie photo |
| **SQL Lab** | Requêtes SQL directes, snippets, historique, vues sauvegardées, export CSV |
| **AI Lab** | Génération IA (Mammouth AI), raffinement, validation des sources, diff côte à côte |
| **Géo-couverture** | Progression par province/état, villes de référence manquantes |
| **Population ref.** | Couverture nationale/régionale, drapeaux, lien carte temps réel |

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Flask (Python 3.12) |
| Base de données | PostgreSQL 16 + PostGIS 3.4 |
| ORM / DB | psycopg 3 (wrapper custom, schéma étoile) |
| Templates | Jinja2 |
| Graphiques | Chart.js |
| Carte | Leaflet.js 1.9 |
| PDF | ReportLab |
| Images | Pillow, Wikipedia/Wikimedia Commons |
| IA | API Mammouth AI (compatible OpenAI) |
| Déploiement | Railway (Gunicorn, 2 workers gthread) |

---

## Démarrage rapide

```powershell
# Cloner et installer
git clone https://github.com/lawiz22/ProjetCITY.git
cd ProjetCITY
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Lancer (PostgreSQL requis via Docker ou Railway)
docker compose --env-file .env.postgres up -d
python run_web.py
# → http://127.0.0.1:5000
```

### Migration depuis SQLite

```powershell
Get-Content .env.postgres | ForEach-Object {
  if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
    [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
  }
}
python scripts\migrate_sqlite_to_postgres.py --pg-dsn "$env:PROJETCITY_DATABASE_URL" --truncate-target
```

---

## Structure du projet

```
run_web.py                     Point d'entrée Flask
app/
  __init__.py                  Factory + auto-migrations
  config.py                   Configuration (env vars)
  db.py                       Connexion DB + migrations
  routes.py                   Routes web + API
  services/
    analytics.py               Métriques, dashboard, SQL
    city_import.py             Import population, périodes, fiches
    city_photos.py             Photos Wikipedia/Commons, EXIF
    event_service.py           Événements historiques CRUD
    mammouth_ai.py             Client API Mammouth AI
    pdf_reports.py             Génération PDF
sql/
  schema_postgres.sql          Schéma PostgreSQL/PostGIS
scripts/                       Scripts de migration, import, validation
data/
  prompts/                     Prompts IA
  city_details/                Fiches texte par ville
templates/web/                 Templates Jinja2
static/
  css/                         Styles
  js/                          Modules JS
  images/                      Photos, drapeaux, événements
```

---

## Modèle de données

Schéma en étoile avec tables de faits et dimensions :

| Table | Rôle |
|-------|------|
| `fact_city_population` | Faits : ville × année × population |
| `fact_region_population` | Faits : région × année × population |
| `fact_country_population` | Faits : pays × année × population |
| `dim_city` | Villes (nom, coordonnées, superficie, densité) |
| `dim_region` | Régions / provinces / états |
| `dim_country` | Pays |
| `dim_time` | Temps (année, décennie, siècle, période) |
| `dim_annotation` | Annotations (label, couleur, photo) |
| `dim_event` | Événements historiques |

14 vues analytiques pré-calculées (croissance, pics, déclins, rebonds, couverture).

---

## Variables d'environnement

| Variable | Description |
|----------|-------------|
| `PROJETCITY_DATABASE_URL` | DSN PostgreSQL |
| `PROJETCITY_SQL_ENABLE_WRITE` | `1` pour activer l'écriture SQL Lab |
| `PROJETCITY_SQL_QUERY_LIMIT` | Lignes max par requête (défaut: 500) |
| `PROJETCITY_SQL_EXPORT_LIMIT` | Lignes max export CSV (défaut: 5000) |

---

## Scripts utilitaires

```powershell
python scripts\build_city_database.py           # Construire la base initiale
python scripts\migrate_sqlite_to_postgres.py     # Migrer SQLite → PostgreSQL
python scripts\import_city_period_details.py     # Recharger les périodes
python scripts\fetch_city_photos.py              # Télécharger photos Wikipedia
python scripts\download_flags.py                 # Télécharger les drapeaux
```
