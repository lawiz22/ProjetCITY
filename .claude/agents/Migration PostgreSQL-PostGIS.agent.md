---
name: Migration PostgreSQL-PostGIS
description: Describe what this custom agent does and when to use it.
tools: Read, Grep, Glob, Bash # specify the tools this agent can use. If not set, all enabled tools are allowed.
---

<!-- Tip: Use /create-agent in chat to generate content with agent assistance -->

Je ferais une migration parallèle, pas une migration “en place”. Le bon principe pour ce repo: on garde l’app Flask vivante, on prépare PostgreSQL/PostGIS à côté, on migre les données, on valide, puis on coupe SQLite.

**Plan**
1. Figer la source de vérité actuelle pendant la migration. La vraie source n’est pas seulement [`data/city_analysis.db`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/data/city_analysis.db), c’est aussi les fichiers `data/city_details`, `data/city_fiches`, `data/country_details`, `data/country_fiches`, `data/region_details`, `data/region_fiches`, les images sous `static/images`, l’historique SQL et les settings IA encore lus/écrits dans [`app/services/analytics.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/services/analytics.py), [`app/services/city_import.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/services/city_import.py), [`app/services/city_photos.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/services/city_photos.py) et [`app/services/mammouth_ai.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/services/mammouth_ai.py). Il faut sauvegarder tout ça avant de toucher au modèle.

2. Introduire une couche DB neutre avant de migrer le SQL. Le premier fichier à casser proprement est [`app/db.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/db.py), parce qu’il est encore 100% `sqlite3`. Je remplacerais le `sqlite3.connect(...)` par un accès PostgreSQL via `psycopg` ou `SQLAlchemy Core`, avec retour en lignes de type dict, puis je déplacerais les paramètres de connexion dans [`app/config.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/config.py) avec un `PROJETCITY_DATABASE_URL`.

3. Créer un schéma PostgreSQL séparé, pas réutiliser directement [`sql/schema.sql`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/sql/schema.sql). Je créerais `sql/schema_postgres.sql` ou mieux une première migration Alembic. Les conversions obligatoires sont simples: `AUTOINCREMENT` vers `BIGSERIAL` ou `GENERATED`, `datetime('now')` vers `timestamptz default now()`, les booléens `0/1` vers `boolean`, `GROUP_CONCAT` vers `string_agg`, `sqlite_master` vers `information_schema`/`pg_catalog`, et `COLLATE NOCASE` vers `lower(...)` ou `citext`.

4. Activer PostgreSQL avec extensions utiles dès le jour 1. J’activerais `postgis`, `unaccent` et `pg_trgm`. `PostGIS` sert tout de suite pour préparer le futur, même si ton front continue encore à lire `latitude/longitude` comme aujourd’hui.

5. Migrer d’abord les tables métiers existantes presque à l’identique. L’ordre safe est: `dim_time`, `dim_annotation`, `dim_country`, `dim_region`, `dim_city`, puis `fact_city_population`, `fact_country_population`, `fact_region_population`, puis les tables de détails, fiches, photos et événements. Ça correspond bien à la dépendance déjà visible dans [`sql/schema.sql`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/sql/schema.sql).

6. Ajouter le spatial sans casser l’app. Dans `dim_city`, je garderais `latitude` et `longitude`, mais j’ajouterais `geom geography(Point, 4326)`. Dans `dim_region` et `dim_country`, j’ajouterais `boundary_geom geometry(MultiPolygon, 4326)` pour le futur. Comme ça, la carte actuelle continue de marcher sans refonte immédiate des templates/JS.

7. Créer trois tables de transition pour sortir les états du filesystem. Je créerais `raw_document` pour stocker les contenus qui vivent aujourd’hui en `.txt`, `sql_saved_view` pour remplacer `saved_views.json`, et `app_setting` pour sortir `mammouth_settings.json`. L’historique SQL peut soit aller dans `sql_query_history`, soit rester temporairement local jusqu’au login, mais je le basculerais vite aussi.

8. Préparer un script d’ETL dédié, séparé du rebuild. Je ne m’appuierais pas sur [`scripts/build_city_database.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/scripts/build_city_database.py) comme source unique, parce qu’il reconstruit depuis des sources Python et peut perdre des enrichissements manuels. Je créerais `scripts/migrate_sqlite_to_postgres.py` qui lit la base SQLite réelle, copie les tables, injecte les `.txt` dans `raw_document`, remplit `geom` depuis `lat/lng`, et compare les comptes de lignes entre les deux bases.

9. Refactorer le read path avant le write path. Le plus sensible après `app/db.py`, c’est [`app/services/analytics.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/services/analytics.py), parce qu’il concentre les requêtes analytiques, les vues, `GROUP_CONCAT`, `sqlite_master`, la gestion d’erreurs `sqlite3.Error` et le SQL Lab. Quand ce fichier est propre en PostgreSQL, la moitié du risque est déjà tombée.

10. Refactorer ensuite le write path. Les priorités sont [`app/services/city_import.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/services/city_import.py), [`app/routes.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/routes.py), [`app/services/city_photos.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/services/city_photos.py) et [`app/services/event_service.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/services/event_service.py). Aujourd’hui, ces fichiers mélangent écritures DB et écritures disque; en version collaborative, la DB et le stockage objet doivent devenir les seules sources de vérité.

11. Adapter les tests avant le cutover. [`tests/conftest.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/tests/conftest.py) et [`tests/test_services.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/tests/test_services.py) sont encore pensés SQLite. Il faut une base PostgreSQL de test et remplacer les assertions sur `sqlite_master`.

12. Faire un cutover en deux temps. D’abord lecture seule sur PostgreSQL avec comparaison des écrans critiques (`/`, `/cities`, `/cities/<slug>`, `/map`, `/events`), puis écriture sur PostgreSQL, puis archivage de SQLite en lecture seule.

**Tables à créer**
- Tables métier à porter 1:1: `dim_annotation`, `ref_population`, `dim_time`, `dim_city`, `dim_city_period_detail`, `dim_city_period_detail_item`, `fact_city_population`, `dim_city_fiche`, `dim_city_fiche_section`, `dim_city_photo`, `dim_event`, `dim_event_location`, `dim_event_photo`, `dim_country`, `fact_country_population`, `dim_country_photo`, `dim_region`, `fact_region_population`, `dim_region_period_detail`, `dim_region_period_detail_item`, `dim_region_photo`.
- Colonnes à ajouter au passage: `dim_city.geom geography(Point,4326)`, `dim_region.boundary_geom geometry(MultiPolygon,4326)`, `dim_country.boundary_geom geometry(MultiPolygon,4326)`.
- Colonnes à ajouter aux tables photo: `object_key`, `storage_provider`, `mime_type`, `file_size`, et idéalement `checksum`.
- Nouvelles tables indispensables: `raw_document(entity_type, entity_slug, document_kind, content, source_origin, created_at, updated_at)`, `sql_saved_view(view_id, name, description, sql, created_at)`, `app_setting(setting_key, setting_value_json, updated_at)`.
- Tables à repousser juste après la migration DB: `user_account`, `role`, `user_role`, `audit_log`, `sql_query_history`.

**Fichiers à refactorer en premier**
- [`app/db.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/db.py) : point d’entrée absolu de la migration.
- [`app/config.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/config.py) : nouvelle config `DATABASE_URL`, stockage, feature flags.
- [`sql/schema.sql`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/sql/schema.sql) : à dupliquer vers une vraie version PostgreSQL.
- [`app/services/analytics.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/services/analytics.py) : vues, agrégations, SQL Lab, introspection SQL.
- [`app/services/city_import.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/services/city_import.py) : upserts, imports, documents `.txt`, géocodage.
- [`app/routes.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/routes.py) : lectures/écritures directes sur disque et quelques requêtes SQL spécifiques.
- [`app/services/city_photos.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/services/city_photos.py) : hypothèse de stockage local à casser.
- [`app/services/mammouth_ai.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/app/services/mammouth_ai.py) : settings IA à sortir du JSON local.
- [`scripts/build_city_database.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/scripts/build_city_database.py) : à conserver pour rebuild, mais à ne pas utiliser comme unique migration.
- [`tests/conftest.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/tests/conftest.py) : fixture PostgreSQL.
- [`tests/test_services.py`](c:/Users/Louis-Martin%20Richard/Documents/ProjetCITY/tests/test_services.py) : remplacer les assertions SQLite.

Le point clé à retenir: je ne commencerais pas par les rôles, et je ne commencerais pas non plus par un ORM complet. Je commencerais par `app/db.py`, `schema_postgres.sql`, puis `analytics.py`, puis l’ETL.

