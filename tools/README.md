# Data tools

Scripts that turn the WordPress site's data into clean, standard data. Run them in order; each
one reads the previous one's output from `data/`.

| Script | Reads | Writes |
|---|---|---|
| `export_wp.py` | the WordPress database, `data/corrections.csv` | `data/wkw.json`, `data/csv/`, `data/reports/export.md` |
| `wikidata.py` | `data/wkw.json`, `data/wikidata-overrides.csv` | `data/wikidata.json`, `data/reports/wikidata.md`, `data/reports/wikidata-review.csv` |
| `build_rdf.py` | `data/wkw.json`, `data/wikidata.json` | `data/rdf/wkw.ttl`, `data/rdf/supplement.ttl`, `data/rdf/wikidata.ttl` |
| `build_site.py` | `data/wkw.json`, `data/rdf/` | the generated parts of the Jekyll site in `docs/` |

## 1. Load the WordPress database

`export_wp.py` reads `_dump/ng_culturalcartography_net.sql` from a throwaway MariaDB container.
`_dump/` holds the original WordPress and MediaWiki install and the database dump. It isn't in
git, because it contains passwords and users' details.

```bash
docker run -d --rm --name wkw-db -e MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1 -e MARIADB_DATABASE=wkw \
  -v "$PWD/_dump/ng_culturalcartography_net.sql:/docker-entrypoint-initdb.d/wkw.sql:ro,Z" \
  docker.io/library/mariadb:10.11
# wait until this prints a number (about a minute), then run the export
docker exec wkw-db mariadb -uroot wkw -e "select count(*) from wp_posts"
python3 -I tools/export_wp.py
docker stop wkw-db
```

Set `WKW_DB_CMD` to use a different database client.

### Corrections

Errors that the export can't fix by itself are listed in `data/corrections.csv`, one per row,
with a note saying why. The export applies them every time it runs, so they survive a fresh
export, and lists them in `export.md`. Each person's record also lists the corrections that
affect it, which become `skos:editorialNote`s in the RDF. To undo one, delete its row.

| action | person | value |
|---|---|---|
| `merge` | the record to keep | a duplicate of it, to merge in |
| `dates` | a person | the corrected birth–death text, e.g. `1770 (Cockermouth, England) – 1850 (Rydal Mount)` |
| `person` | a new person's id | their name: for someone WKW's links need but has no record for |
| `unlink` | a person | someone they're linked to, to remove the link |
| `link` | a person | someone to link them to |

## 2. Reconcile with Wikidata

```bash
uv run --no-project --with requests python -I tools/wikidata.py
```

This calls the Wikipedia and Wikidata APIs and caches every response in `tools/.cache/`, so later
runs only fetch what has changed. Delete the cache to fetch everything again.

To confirm or correct a match, add a row to `data/wikidata-overrides.csv` and re-run:

```csv
person,qid,note
charles-babbage,Q46633,checked
some-person,none,not on Wikidata
```

Search matches with medium or low confidence are then checked against the people WKW says
the person knew. A match is *corroborated* if Wikidata records a relationship with one of them,
or either person's English Wikipedia article links to the other's.

## 3. Build RDF

```bash
uv run --no-project --with rdflib python -I tools/build_rdf.py
```

- `wkw.ttl` is WKW's own data. People are linked with plain `foaf:knows`. The Wikidata match is
  `owl:sameAs` if it is high confidence, checked or corroborated, and `skos:closeMatch` otherwise.
- `supplement.ttl` holds birth and death dates and places that WKW doesn't give, taken from
  Wikidata in the same terms as `wkw.ttl`. It only uses `owl:sameAs` matches, and only where
  Wikidata gives a single value. Occupations aren't borrowed.
- `wikidata.ttl` is what Wikidata says about every matched person, in Wikidata's own terms.

## 4. Build the site

```bash
python3 -I tools/build_site.py
cd docs && bundle exec jekyll build    # or: bundle exec jekyll serve
```

`build_site.py` writes the site's data (`docs/_data/people.json`, `names.json`, `latest.json`),
a page for each person with a bio (`docs/names/`), the profession pages (`docs/types/`), and the
files the search, field and query pages load (`docs/assets/data/`). It replaces those each time,
so they shouldn't be edited by hand. Everything else in `docs/` is edited directly.

`import_pages.py` copied the WordPress site's other pages (the about pages, the blog, the 404
page) into `docs/` once. It read them from a copy of the WordPress site running locally, which
needs the database container from step 1 (started with `-p 127.0.0.1:8099:80`) and WordPress
alongside it, with a local `wp-config.php` (database `wkw`, user `root`, no password, host
`127.0.0.1`, and `WP_HOME` and `WP_SITEURL` set to `http://localhost:8099`) and WordPress's
usual rewrite rules in an Apache config file, as the dump has no `.htaccess`:

```bash
docker run -d --rm --name wkw-wp --network container:wkw-db \
  -v "$PWD/_dump/culturalcartography.net/httpdocs:/var/www/html:ro,Z" \
  -v "/path/to/wp-config.php:/var/www/html/wp-config.php:ro,Z" \
  -v "/path/to/wp-rewrite.conf:/etc/apache2/conf-enabled/wp-rewrite.conf:ro,Z" \
  docker.io/library/wordpress:php8.3-apache apache2-foreground
```

## 5. Suggest relationship types (dropped)

Nat reviewed the start of the sheet this produced and decided against classifying WKW's
relationships with any vocabulary: links stay as plain `foaf:knows`. The script and
`data/link-types/` are kept only as a record of what was tried.

`type_links.py` asks Claude (Sonnet 5.5) to type each link from the bios, using the RELATIONSHIP
vocabulary plus a few WKW terms, and to flag anything that doesn't fit. It needs
`ANTHROPIC_API_KEY`, which `~/.bashrc` only sets for interactive shells, hence `bash -ic`:

```bash
T='uv run --no-project --python 3.12 --with anthropic python -I tools/type_links.py'
bash -ic "$T count --model claude-sonnet-5-5"     # exact input tokens (free)
bash -ic "$T submit --model claude-sonnet-5-5"    # the whole job as a Message Batch (~$10)
bash -ic "$T collect --model claude-sonnet-5-5"   # once it has ended, saves data/link-types/run-v3-...jsonl
bash -ic "$T repair data/link-types/run-v3-claude-sonnet-5-5-medium.jsonl --model claude-sonnet-5-5"
$T evaluate data/link-types/run-v3-claude-sonnet-5-5-medium.jsonl   # checks, and agreement with Wikidata
$T sheet data/link-types/run-v3-claude-sonnet-5-5-medium.jsonl      # the CSV for review
```

Bump `PROMPT_VERSION` in the script whenever the instructions or types change, so runs don't mix.
