# ProjetCITY

Base locale d'analyse urbaine pour villes canadiennes et américaines.

## Plateforme web analyste

Une première version web locale est maintenant disponible avec Flask + Jinja.

### Fonctionnalités livrées

- dashboard analytique avec indicateurs clés
- annuaire des villes avec population récente et pic historique
- annuaire des villes avec double affichage: vue blocs illustrée et vue liste compacte
- fiche détaillée par ville avec courbe démographique, annotations et périodes narratives
- fiche détaillée par ville avec header photo premium, badges de synthèse et résumé narratif
- fiche détaillée par ville avec navigation rapide par ancres vers Courbe, Annotations, Timeline et Export
- fiche détaillée par ville avec bouton flottant de retour en haut
- fiche détaillée par ville avec mode lecture guidée période par période
- fiche détaillée par ville avec barre de lecture guidée flottante, autoplay lent et vue complète explicite
- comparaison multi-villes
- zoom, pan et réinitialisation sur les courbes de comparaison et de détail
- export PNG des graphiques principaux
- SQL Lab pour lancer des requêtes SQL directement sur la base SQLite
- export CSV depuis le SQL Lab pour les requêtes en lecture
- historique persistant des requêtes SQL avec rechargement rapide
- sauvegarde de vues analytiques SQL personnalisées
- carte analytique des villes avec bulles proportionnelles à la population récente
- filtres dynamiques directement sur la carte
- couches thématiques sur la carte: population, croissance, déclin, pics, annotations
- export PDF du dashboard et des fiches ville
- export PDF ville enrichi avec photo locale
- export PDF ville enrichi avec photo locale et badges de synthèse en tête
- tableaux triables et filtrables côté client
- annotations temporelles cliquables sur la carte et dans les courbes des fiches ville
- bandes verticales colorées sur les graphiques des villes pour matérialiser les annotations historiques
- filtres à cocher sur les annotations des fiches ville pour afficher, masquer et réafficher librement les événements voulus
- cache local d'images par ville dans static/images/cities/
- timeline visuelle pour les périodes détaillées des fiches ville
- repères d'annotations directement reliés aux périodes dans la timeline des fiches ville
- surbrillance croisée web entre période, annotation et bande graphique active
- bouton par période pour n'ouvrir que les annotations liées puis retour fiable à la vue complète

### Lancer l'application web

Sous Windows PowerShell:

1. Activer l'environnement: `\.venv\Scripts\Activate.ps1`
2. Vérifier que la base existe: `python scripts\build_city_database.py`
3. Lancer le serveur web: `python run_web.py`
4. Ouvrir le navigateur sur `http://127.0.0.1:5000`

Pour générer ou rafraîchir les images locales des villes depuis Wikipedia/Wikimedia:

`python scripts\fetch_city_photos.py`

### Variables d'environnement disponibles

- `PROJETCITY_DATABASE_PATH` : chemin alternatif vers la base SQLite
- `PROJETCITY_SQL_QUERY_LIMIT` : nombre maximal de lignes retournées par instruction SQL Lab
- `PROJETCITY_SQL_EXPORT_LIMIT` : nombre maximal de lignes exportées en CSV depuis le SQL Lab
- `PROJETCITY_SQL_HISTORY_PATH` : chemin du fichier local de persistance de l'historique SQL
- `PROJETCITY_SQL_HISTORY_LIMIT` : nombre maximal d'entrées conservées dans l'historique SQL
- `PROJETCITY_SAVED_VIEWS_PATH` : chemin du fichier local des vues analytiques sauvegardées
- `PROJETCITY_SAVED_VIEWS_LIMIT` : nombre maximal de vues personnalisées sauvegardées
- `PROJETCITY_SQL_STATEMENT_LIMIT` : nombre maximal d'instructions par exécution SQL Lab
- `PROJETCITY_SQL_ENABLE_WRITE` : mettre `1` pour autoriser les requêtes SQL en écriture dans SQL Lab

Par défaut, le SQL Lab accepte les requêtes en lecture (`SELECT`, `WITH`, `PRAGMA`).
Le mode écriture est désactivé tant que `PROJETCITY_SQL_ENABLE_WRITE=1` n'est pas défini.

## Ce qui est déjà en place

- un environnement virtuel local `.venv`
- une base SQLite locale dans `data/city_analysis.db`
- un schéma en étoile / snowflake minimal avec 6 tables:
  - `fact_city_population`
  - `dim_city`
  - `dim_time`
  - `dim_annotation`
  - `dim_city_period_detail`
  - `dim_city_period_detail_item`
- une dimension détaillée des périodes urbaines à partir des fichiers `.txt`
- une vue analytique prête à interroger: `vw_city_population_analysis`
- cinq vues analytiques supplémentaires prêtes à l'emploi
- un script d'import qui lit automatiquement `villestats.py` et `villestats_v2.py`
- un script de correction pour remettre à niveau une base déjà créée

## Structure

- `villestats.py` : script source avec les séries historiques et annotations
- `villestats_v2.py` : version simplifiée du fichier source
- `run_web.py` : point d'entrée du serveur web Flask local
- `app/` : application web Flask, routes et services analytiques
- `scripts/build_city_database.py` : construit et recharge la base SQLite à partir de `villestats.py` et `villestats_v2.py`
- `scripts/import_city_period_details.py` : recharge uniquement les périodes détaillées depuis les `.txt`
- `scripts/validate_villestats.py` : valide les nouvelles villes ajoutées dans `villestats.py`
- `scripts/validate_villestats_v2.py` : valide le format simplifié de `villestats_v2.py`
- `scripts/validate_city_period_details.py` : valide les fichiers `.txt` de périodes détaillées
- `sql/schema.sql` : schéma SQL
- `data/city_details/` : fichiers texte détaillés par ville
- `data/city_analysis.db` : base locale générée
- `templates/web/` : templates Jinja de la plateforme web
- `static/` : CSS et JavaScript de l'interface analyste

## Modèle actuel

### `fact_city_population`
Table centrale pour l'analyse:
- clé ville
- clé de temps
- année
- population
- indicateur d'année clé
- lien optionnel vers une annotation

### `dim_city`
Dimension ville:
- nom court de la ville sans suffixe d'état ou de province
- slug analytique
- région / province / état dans un champ séparé
- pays
- couleur associée à la ville
- fichier source

### `dim_time`
Dimension temporelle:
- année
- décennie
- tranche de 25 ans
- tranche de 50 ans
- siècle
- période historique analytique

### `dim_annotation`
Dimension descriptive:
- texte de l'annotation
- couleur unique associée à l'annotation
- type d'annotation

### `dim_city_period_detail`
Dimension détaillée des périodes par ville:
- ville liée à `dim_city`
- ordre de période dans le récit
- libellé de période source
- titre de période
- année de début et de fin
- texte détaillé consolidé
- fichier source `.txt`

### `dim_city_period_detail_item`
Sous-dimension de détail par période:
- une ligne par point de détail
- ordre d'apparition dans le fichier texte
- texte détaillé brut

### `vw_city_population_analysis`
Vue prête pour les analyses SQL:
- joint automatiquement `fact_city_population`
- ajoute les attributs de `dim_city`
- ajoute les attributs de `dim_time`
- ajoute les annotations quand elles existent

## Vues analytiques prêtes à l'emploi

- `vw_city_population_analysis` : vue détaillée complète
- `vw_city_growth_by_decade` : croissance absolue et relative par décennie
- `vw_city_peak_population` : pic démographique par ville
- `vw_city_decline_periods` : périodes de déclin entre deux observations
- `vw_city_rebound_periods` : périodes de reprise après stagnation ou recul
- `vw_annotated_events_by_period` : événements annotés avec contexte temporel
- `vw_city_period_detail_analysis` : lecture analytique des périodes détaillées importées depuis les `.txt`
- `vw_city_period_detail_with_population` : périodes détaillées enrichies avec population début/fin, années de correspondance les plus proches et variation
- `vw_city_period_detail_with_annotations` : périodes détaillées enrichies avec populations et annotations couvertes par la période

## Recharger la base

Sous Windows PowerShell:

1. Activer l'environnement: `.\.venv\Scripts\Activate.ps1`
2. Valider le fichier source: `python scripts\validate_villestats.py`
3. Valider la version simplifiée si utilisée: `python scripts\validate_villestats_v2.py`
4. Recharger la base: `python scripts\build_city_database.py`

Pour recharger seulement les fichiers texte de périodes détaillées:

`python scripts\import_city_period_details.py`

Pour valider les fichiers texte de périodes détaillées:

`python scripts\validate_city_period_details.py`

Pour la version simplifiée:

1. Activer l'environnement: `.\.venv\Scripts\Activate.ps1`
2. Valider le fichier: `python scripts\validate_villestats_v2.py`

## Corriger une base existante

Si tu veux remettre à niveau une base déjà créée avec l'ancien schéma:

`python scripts\repair_city_dimension.py`

## Exemple de requête

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

## Idées pour la suite

Quand tu voudras aller plus loin, on pourra ajouter d'autres dimensions/faits pour:
- migrations interurbaines
- déplacements domicile-travail
- immobilier / loyers / prix
- emploi et revenus
- transport collectif
- émissions et usage du sol
- événements historiques majeurs

Cela permettra de répondre à des questions sur l'étalement, l'exode, la reprise des centres-villes et les trajectoires métropolitaines dans le temps.
