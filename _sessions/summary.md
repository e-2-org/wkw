# Session: getting Who Knew Whom's data out of WordPress - summary

**Dates:** 19–20 October 2026
**Repo:** `repos/wkw`, not yet a git repo. The WordPress theme is in `repos/wkw-theme` (Bitbucket `p-2/wkw-theme`).

The transcript is in [transcript.md](transcript.md).

*Who Knew Whom* (culturalcartography.net) is Nat Goodden's research into who knew whom among more than 3,000 figures in the arts and sciences. It started as a MediaWiki site and became WordPress, with a custom post type for names and ACF fields for links between names and to outside sources.

The long-term aim is:
- a FOAF triplestore that can be searched with SPARQL
- a force-directed graph set in the project's font (Handsome Pro, licensed for website use)

This session:
- surveyed what already existed
- exported and cleaned the data
- matched people to Wikidata
- built RDF
- used Claude (Sonnet 5.5) to suggest what kind of relationship each link is, with a review sheet for Nat

## What was there already

- **The theme** has:
  - a `wkwname` post type and a Professions taxonomy
  - ACF fields: first and last name, sort key, alternate name, `birth_death` as free text, linked names, outside links, and "disambiguation" names
  - a save hook that makes links two-way
  - a REST API, including `/d3/{id}`, which returns the two-hop network around a person
  - a d3 v4 force-graph prototype (`js/wkw.js`) with a bio panel
  - the importer and "munger" that split the MediaWiki text into fields
- **The MediaWiki database** (`ng_wkwwiki`) is not in the dump. Only the WordPress one is.
- **The network:** 3,469 of the 3,481 names form a single connected network. Links between names are untyped: they say only that two people knew each other.

## What was done

- **Moved the original site into `_dump/`.** The WordPress and MediaWiki install and `ng_culturalcartography_net.sql` are there, and `.gitignore` excludes it, because it contains database passwords and users' password hashes. `tools/.cache/` is also ignored.
- **Export (`tools/export_wp.py`).** It reads the dump from a throwaway MariaDB container and writes:
  - `data/wkw.json`
  - `data/csv/` (people, knows, sources, disambiguation)
  - `data/reports/export.md`

  Clean-up:
  - **Merged 26 duplicate records.** In 2018 the MediaWiki import created a stub for every name; some names were then added again by hand, sometimes without accents. The spelling with accents is kept.
  - **Named three records that had no title** from their first and last name fields: J. M. Barrie and Jørn Utzon (twice).
  - **Dropped 8 links to deleted posts** and one empty draft (Lucio Fontana).
  - **Parsed every `birth_death` value** into year, place, *c.* and "?" (uncertain place). The original text is kept.
  - **Result:** 3,453 people (1,295 with bios, 2,158 stubs) and 12,400 acquaintanceships.
- **Wikidata (`tools/wikidata.py`).** Matched 3,250 of 3,453 people:

  | How | Count |
  |---|---|
  | From Nat's Wikipedia links | 1,101 |
  | Search, high confidence | 380 |
  | Search, medium confidence | 1,726 |
  | Search, low confidence | 43 |
  | Unmatched | 203 |

  - **Matching:** search candidates are scored on name and years. They must also have been alive at the same time as the people they are said to have known.
  - **Data fetched:** dates, places with coordinates, occupations, portraits, authority IDs (VIAF, ULAN, ISNI, LC, GND, BnF), and 3,527 relationships Wikidata records between matched people.
  - **Outputs:** `data/wikidata.json`, `data/reports/wikidata.md` and `wikidata-review.csv`. Corrections go in `data/wikidata-overrides.csv`.
- **RDF (`tools/build_rdf.py`).**
  - `data/rdf/wkw.ttl` holds Nat's data, about 81k triples using FOAF, schema.org and SKOS. Low-confidence matches get `skos:closeMatch` rather than `owl:sameAs`.
  - `data/rdf/wikidata.ttl` holds Wikidata's facts, about 76k triples using Wikidata's own `wdt:` properties.
  - Both load into Oxigraph in 0.3 seconds, and test SPARQL queries joining the two return in milliseconds.
- **Relationship types (`tools/type_links.py`).**
  - **Vocabulary:** the RELATIONSHIP vocabulary plus a few `wkw:` terms: correspondedWith, classmateOf, patronOf, portrayed, relativeOf, unspecified.
  - **The model returns,** for each link: the types, an exact quote, a confidence level, and a categorised discrepancy flag.
  - **Requests:** one per person with a bio, 1,244 in all. A link between two people with bios is handled once, with both bios included.
  - **Pilot:** 50 bios each on Haiku and Sonnet. Sonnet was a little better on nuance and quoting.
  - **Changes Pete asked for after the pilot:** "has met" merged into acquaintance; acquaintance preferred over friend or colleague when unsure; anything that doesn't fit Nat's material flagged.
  - **Full run:** Sonnet 5.5 through the Message Batches API, then a direct re-run of 111 links that had failed or been left out.
  - **Review sheet:** `data/link-types/review-run-v3-claude-sonnet-5-5-medium.csv`, with 12,400 rows.

## Results worth knowing

- **Wikidata found 34 more likely duplicates** that differ only in spelling or transliteration, such as Bertholt/Bertolt Brecht and C. G. Jung / Carl Jung / Carl Gustav Jung. The link typing found another: Henry/Henri Chopin. None of these have been merged yet.
- **20 dates disagree with Wikidata.** Several are typos, such as Wordsworth dying in 1950, Daumier in 1979, Curie born in 1897 and Boetti in 1640.
- **Link types.** The suggestions agree with 80% of Wikidata's relationships, leaving out "influenced by", which Wikidata uses for intellectual influence.
  - **Reversed directions:** a birth-year check flagged 112 links where a "teacher" or "parent" was born after the pupil or child. Most are simply reversed. Some reveal a wrong-person link: Bewick's pupil William Harvey (the engraver) is linked to William Harvey the physician.
  - **Model flags:** never met 118, contradiction 187, ambiguous name 537, dates 165, other 529, not mentioned 2,886.
  - **Unspecified:** 23% of links, where the bios don't describe the relationship.
- **Correction:** the "1,709 one-way links" reported early in the session were a counting mistake. WordPress stores return links as integers, and the quick count only read strings. The links really are two-way.

## Costs

The Anthropic API account was set up during the session with $20 credit.

| Step | Cost |
|---|---|
| Token counting | free |
| Pilots | ~$1.27 |
| Full batch | $9.74 |
| Repair run | $0.20 |
| **Total** | **~$11.20** |

About $8.80 of credit is left.

## Decisions

- `_dump/` (the original install and database) stays out of git.
- Link typing used Sonnet 5.5 as a batch, not Opus or Haiku.
- "Has met" is merged into "acquaintance", and the model leans towards "acquaintance" when unsure.
- Suggested types are only suggestions. Nothing changes the main data until Nat has reviewed them.
- Teacher/parent directions that fail the birth-year check are flagged, not flipped.

## Open items

- Nat to review `review-run-v3-…csv`, following `data/link-types/readme.md` (being sent with the CSV on 20 October).
- Nat to review `wikidata-review.csv` (the 203 unmatched and 43 low-confidence people) and the date mismatches. This sheet isn't covered by the readme.
- When the review sheet comes back: read the `decision` column (`ok`, corrected types, `reverse`, `wrong person`, `remove`, or blank for not reviewed) and turn it into typed links, declaring the `wkw:` terms as `rdfs:subPropertyOf foaf:knows` like the RELATIONSHIP ones.
- Merge the duplicates once they're confirmed. Re-run the export and Wikidata steps, then rebuild the RDF.
- Turn Nat's decisions into typed links in the RDF.
- Set up the repo: `git init` and an `e-2-org/wkw` repo (private until Pete decides otherwise), with the `docs/` site layout.
- Confirm the RDF base URI. It currently assumes `https://culturalcartography.net/names/<slug>/#person`.
- Later: the static site, SPARQL in the browser (Oxigraph WASM), graph views (d3 SVG around one person, plus a whole-network map), and a "how did X know Y?" path finder.
- Find the MediaWiki database if a copy exists.

## Later on 20 October: instructions for Nat

- **`data/link-types/readme.md`** explains the review sheet to Nat:
  - how the data was reconciled (the clean-up, the Wikidata matching and the link typing)
  - what each column means
  - how to fill in `decision` and `notes`
  - which rows to start with
  - the relationship types
  - what the typed links are for

  Pete is sending it to Nat with the CSV.
- **Row ranges in the sheet,** in its saved order:
  - 2–113: failed the birth-year check
  - 114–1620: flagged by the model
  - 1621–4505: not mentioned in either biography
  - 4506–12401: nothing flagged, least certain first

  Sorting the CSV changes these.
- **The `decision` values** were proposed by Claude, as nothing had been agreed: `ok`, corrected types, `reverse`, `wrong person`, `remove`, or blank for not reviewed.
- **RELATIONSHIP and FOAF:** RELATIONSHIP's properties are all `rdfs:subPropertyOf foaf:knows`, so typed links still count as `foaf:knows`.

## Security note

During the session an API key was briefly exposed through an editor selection. Pete replaced it with a new key, and it is redacted from the transcript. `~/.bashrc` only sets `ANTHROPIC_API_KEY` for interactive shells, so the scripts are run with `bash -ic`.

---

# 3 November 2026: corrections, Wikidata, and the Jekyll site

**Branch:** `main` for the data work, then `jekyll-site` for the site (to be merged through a pull request)
**Commits:** `d1e8b55`, `2c88200` on `main`; `757f821`, `12f094f`, `d2b91e7`, `8b39731` and the `docs/pages/` reorganisation on `jekyll-site`

The same Claude Code session also worked on minus20's slider, which is recorded in that repository.

## Nat's reply

Nat reviewed the start of the relationship-typing sheet and decided against classifying WKW's relationships with any vocabulary: links stay as plain `foaf:knows`. Nat also resists a definitive list of professions, but sees a use for checking WKW against outside sources to catch obvious slips, such as Wordsworth's death being a century out. The Word document Nat mentioned wasn't attached.

## Data: errors corrected

- **`data/corrections.csv`**, applied by `export_wp.py` every time it runs, one row per correction with its reason. Each person's record lists the corrections that affect it, which become `skos:editorialNote`s in the RDF. To undo one, delete its row.
  - **39 duplicate records merged** (36 groups found through Wikidata, plus Henry/Henri Chopin), such as Bertholt/Bertolt Brecht and three Carl Jungs: 3,453 people became 3,416. Other spellings are kept as other names.
  - **13 date typos fixed** where Wikidata agreed: Wordsworth 1950→1850, Curie, Daumier, Einstein, Boetti, Jongkind, Martius and others.
  - **Two links moved to the right person**, adding two people: Bewick's pupil William Harvey the engraver (not the physician who died in 1657), and Magnol's pupil Antoine de Jussieu (not his nephew, born after Magnol died).
  - **Four links removed** between people whose lifetimes didn't overlap: Boscovich–Carl Jacobi (perhaps F. H. Jacobi, for Nat to decide), Rowland Hill–Richard Price, Faraday–Valéry, Fanny Mendelssohn–Massenet. Two of these come from Nat's bios, which are unchanged.
- **The export** also repairs a URL pasted onto another (Jonathan Swift's), orders professions the same way every run, and keeps each person's acquaintances in the order Nat listed them.
- **7 date disagreements with Wikidata were left alone.** For Kelvin (1824), Piazzi Smyth (1819) and Flamsteed (1719, Old Style), WKW is right and Wikidata wrong; the others are disputed.

## Data: filled in from Wikidata

- **Corroboration (`wikidata.py`).** A medium or low search match now counts only if Wikidata records a relationship with someone WKW says the person knew, or either person's English Wikipedia article links to the other's. 1,383 of 1,731 passed. The rest are `skos:closeMatch` in the RDF instead of `owl:sameAs`.
- **`data/rdf/supplement.ttl`** holds birth and death dates and places that WKW doesn't give, from trusted matches only, where Wikidata gives one value, in the same terms as `wkw.ttl`. Occupations aren't borrowed, following Nat. Dates giving an impossible lifespan are skipped (Wikidata has James Rosenquist born in 1547).
- **People with dates:** 1,493 → 2,873 of 3,416.

## Git

Pete made `wkw` a git repository (`e-2-org/wkw`, public). The data was committed in two steps so the corrections show as a diff: first the October state (`d1e8b55`), using a copy of `data/` saved before the changes and the scripts with this session's edits reversed (checked by re-running them, which reproduced the October data apart from the order of professions), then this session's changes (`2c88200`).

## The Jekyll site (`docs/`, branch `jekyll-site`)

- **Same pages and URLs as WordPress:** home with the latest additions, the list of names, a page for each of the 1,295 people with a bio, the profession pages (ten to a page), and the about pages, blog post, author, category and 404 pages.
- **Same design:** GeneratePress's, GP Premium's and the WKW theme's stylesheets, scripts, fonts (Handsome Pro) and images, plus the CSS WordPress put inline, loaded in WordPress's order. The order matters: the phone menu broke until it was kept.
- **How it was checked:** the original site was run locally (the dump's WordPress and database in containers, with a local `wp-config.php` and rewrite rules) and compared by screenshot. 37 of 52 sampled pages matched pixel for pixel below the menu; the rest differ only by corrected data, the now-alphabetical names list, and the spacing of other names.
- **Faithful details:** curly quotes as WordPress's `wptexturize` made them in bios and titles; the names list sorted properly (WordPress put names without a sort key first); "film director" and "film-director" share one profession page.
- **Search** runs in the browser over names and bios (`assets/data/search.json`).
- **Field** (`/field/#id`, first called "graph"): the WKW theme's unfinished d3 force graph, finished and ported to d3 v7. One person, who they knew, and who those people knew; double-click to recentre; click a name for the bio panel. Each person's page links to their field.
- **Network** (`/network/`): everyone at once in WebGL with sigma.js 3, laid out live by ForceAtlas2 in a worker for 30 seconds. Everyone starts at their (estimated) birth year, left to right, which lets the layout unfold into two halves, roughly earlier centuries and the 20th century; from a random start it tangled into a ball. Point at someone to see who they knew; click for the bio panel; a find box zooms to anyone. Sigma 4 was tried and dropped: its new styling API is too recent.
- **Query** (`/query/`, first called "sparql"): SPARQL with Oxigraph (WebAssembly) in a worker, over `wkw.ttl`, `supplement.ttl` and `wikidata.ttl` as three named graphs queried together. It loads in under a second. Twelve tested examples are in `_data/sparql_examples.yml`; queries are kept in the URL, results link to people's pages, Commons portraits show as thumbnails, and results download as CSV.
- **Layout:** every page is one file in `docs/pages/` with a `permalink` (`pages/names/<id>.html` is `/names/<id>/`), instead of a folder per URL. The built site was identical before and after the move.
- **Tools:** `tools/build_site.py` generates the site's data, name and profession pages, and the search, graph and RDF files; `tools/import_pages.py` copied the ordinary pages from the running WordPress site once; `tools/field-bundle/` bundles sigma, graphology and ForceAtlas2 with esbuild.

## Decisions

- No relationship vocabulary: links are plain `foaf:knows`.
- No occupations borrowed from Wikidata.
- Corrections are kept as data (`corrections.csv`), not edits to the database dump.
- The menu reads search, about, blog, contact, field, network, query. The odd existing labels ("search" opens the "what Who Knew Whom is" page, "blog" opens "questions") are kept as WordPress had them. The empty contact page stays empty.
- Pages keep the theme's see-through sticky menu, as WordPress showed it.

## Open items

- Merge `jekyll-site` into `main` through a pull request; then switch on GitHub Pages (`main`, `/docs`). The repo is already public. Nat may want to see the site first.
- Nat to decide on the Boscovich–Jacobi link, and perhaps reword the Hill and Fanny Mendelssohn bios.
- Nat to review the 201 unmatched people and the 348 uncorroborated matches (`data/reports/wikidata-review.csv`).
- Wikidata errors that could be reported upstream: Kelvin's and Piazzi Smyth's birth years, Rosenquist's birth date, Louis Bretez's dates.
- The field's centre gets crowded for well-connected people (the prototype's force settings were kept).
- Not tested on a real phone, or in Safari or Firefox.
