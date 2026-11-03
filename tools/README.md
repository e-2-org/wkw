# Data tools

Scripts that turn the WordPress site's data into clean, standard data. Run them in order; each
one reads the previous one's output from `data/`.

| Script | Reads | Writes |
|---|---|---|
| `export_wp.py` | the WordPress database | `data/wkw.json`, `data/csv/`, `data/reports/export.md` |
| `wikidata.py` | `data/wkw.json`, `data/wikidata-overrides.csv` | `data/wikidata.json`, `data/reports/wikidata.md`, `data/reports/wikidata-review.csv` |
| `build_rdf.py` | `data/wkw.json`, `data/wikidata.json` | `data/rdf/wkw.ttl`, `data/rdf/wikidata.ttl` |

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

## 3. Build RDF

```bash
uv run --no-project --with rdflib python -I tools/build_rdf.py
```

## 4. Suggest relationship types (costs money)

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
