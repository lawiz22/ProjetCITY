# ProjetCITY

Base locale d'analyse urbaine pour villes canadiennes et américaines.

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
- `scripts/build_city_database.py` : construit et recharge la base SQLite à partir de `villestats.py` et `villestats_v2.py`
- `scripts/import_city_period_details.py` : recharge uniquement les périodes détaillées depuis les `.txt`
- `scripts/validate_villestats.py` : valide les nouvelles villes ajoutées dans `villestats.py`
- `scripts/validate_villestats_v2.py` : valide le format simplifié de `villestats_v2.py`
- `scripts/validate_city_period_details.py` : valide les fichiers `.txt` de périodes détaillées
- `sql/schema.sql` : schéma SQL
- `data/city_details/` : fichiers texte détaillés par ville
- `data/city_analysis.db` : base locale générée

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
