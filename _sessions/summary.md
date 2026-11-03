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
