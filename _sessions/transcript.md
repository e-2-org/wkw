# Session: getting Who Knew Whom's data out of WordPress - transcript

**Dates:** 19–20 October 2026
**Participants:** Pete (user), Claude (assistant)

The summary is in [summary.md](summary.md). Pete's messages are quoted in full; Claude's replies and work are condensed. An API key that appeared in the conversation has been redacted.

---

## 19 October 2026

### Ideas for taking the project forward

**Pete:** I have another project in repos/wkw - this is my favourite so I've been leaving it until last. It is curently a wordpress site, but started as a Mediawiki site. The wordpress theme (in repos/wkw-theme as well as the dump in repos/wkw) defines a custom post type to handle "names" and data associated with them. The project was undertaken by artist Nat Gooden who was fascinated by the relationships between historical figures - he collected information about over 3000 people and how they related to each other. The WordPress theme defines additional fields to store these links to other names and other links to external sources of information. Eventually, I want this to become a large triplestore using the FOAF vocabulary which is searchable using SPARQL queries and can display in the project's font as a force directed graph (or similar) using d3 (or another alternative). I'm not sure how far I got with this project but I'd love to get some ideas from you on how I can take it forwards

**Claude:** Surveyed both repos.

- **The theme** has:
  - a `wkwname` post type, a Professions taxonomy and ACF fields
  - a hook that makes links two-way
  - a REST API with a `/d3/{id}` endpoint
  - a d3 v4 force-graph prototype with a bio panel
  - a MediaWiki importer and the "munger"
- **The database:** loaded the SQL dump into a temporary MariaDB container. It has 3,481 names (1,295 published with bios, 2,185 "pending" stubs), about 12,400 links, 263 professions and about 3,600 outside links (1,068 to English Wikipedia). The MediaWiki database isn't included.
- **The network:** 3,469 of the 3,481 names form one connected network.

Ideas offered:
- export the data and clean it
- reconcile it with Wikidata
- type the links from the bios with an LLM, using the RELATIONSHIP vocabulary
- a Jekyll site on GitHub Pages
- RDF built at publish time
- SPARQL in the browser with Oxigraph WASM
- d3 SVG around one person plus a sigma.js map of the whole network
- a "how did X know Y?" path finder, a time slider, and links in the bios

Claude also reported "1,709 one-way links", which turned out to be wrong; it was corrected later.

### Priorities

**Pete:** I don't think Nat is still adding names, but that doesn't mean he isn't still compiling data - I don't think he got on with WordPress. Yes, the Handsom Pro license was specifically for hosting on a website, but it was purchased some time ago. My main concern is getting the data into a standard format and cleaning it, and getting as many external Wikidata references in place to reconcile the data (like the birth and death dates and locations) to enrich it where possible  I love the idea of getting an LLM to suggest types for links between people

**Claude:** Built three scripts in `repos/wkw/tools/`.

1. **`export_wp.py`** writes `data/wkw.json`, CSVs and an export report.
   - *The one-way links:* checking them showed that WordPress stores return links as integers and the first count only read strings. The links are really two-way.
   - *Duplicates:* found two kinds. The 2018 import made a stub for every name and some were then added again by hand; others differ only in accents. 26 were merged by comparing names without accents, keeping the spelling with accents.
   - *Untitled records:* three, J. M. Barrie and Jørn Utzon, were named from their first and last name fields.
   - *Dates:* every `birth_death` value was parsed, including bracketed places, *c.*, "?" and "unknown".
   - *Result:* 3,453 people and 12,400 links.
2. **`wikidata.py`** has three stages: Nat's Wikipedia links; name search scored on years; and a check that a candidate was alive at the same time as the people they're said to have known. Every response is cached.
   - *First run:* 3,180 matched. Loosening the acceptance margin slightly for English Wikipedia title matches raised it to 3,250 of 3,453.
   - *Also found:* 34 more duplicates by spelling or transliteration, 20 dates that disagree with Wikidata (including Wordsworth's death given as 1950), and 3,527 relationships between matched people.
3. **`build_rdf.py`** writes `wkw.ttl` (FOAF, schema.org and SKOS) and `wikidata.ttl` (`wdt:` properties). rdflib's SPARQL was too slow, so the files were tested with Oxigraph instead. They load in 0.3 seconds, and queries joining the two files work.

Claude suggested keeping the WordPress and MediaWiki install out of git, because `wp-config.php`, `LocalSettings.php` and the SQL dump contain credentials.

### Moving the dump, and a cost estimate

**Pete:** If you can gfet an estimate that would be great. Can you move the contents of the wkw folder (wordpress / mediawiki bum and database to a _dump folder and gitignore it

**Claude:**
- Moved `culturalcartography.net/` and the SQL file into `_dump/`, and added `.gitignore` for `_dump/`, `tools/.cache/` and `__pycache__/`. Updated the README's database path. Didn't run `git init`.
- Loaded the claude-api skill for current prices.
- Estimated from character counts: one request per bio, 12,400 links, every link involving at least one bio. Opus 5.5 about $28 as a batch, Sonnet 5.5 about $14, Haiku 5.5 about $0.70.
- Suggested a pilot first, plus an exact count from the free token-counting endpoint.

**Pete:** I've never done that

**Claude:** Checked: no `ant` CLI and no `ANTHROPIC_API_KEY`. Explained that API use is billed separately from a Claude subscription, and how to set up an account: create it in the Console, add credit, set a spend limit, create a key, and put it in `~/.bashrc`, not in the chat.

**Pete:** OK - I've added the API key and $20 credit

*(The key was also selected in an unsaved editor tab, so it reached the conversation. Redacted here.)*

**Claude:** Explained that the key had reached the conversation through the editor selection, and that session transcripts are saved in the repo. Advised revoking it and creating a new one, closing the tab without saving, and restarting VS Code. Also noted that the key didn't start with the usual `sk-ant-api03-` prefix.

**Pete:** OK

**Claude:**
- The new key was in `~/.bashrc` but still invisible to Claude's shell, because `.bashrc` stops early for non-interactive shells (line 8) and the key is on line 135.
- Ran commands through `bash -ic` instead. A free model-list call returned HTTP 200.
- Wrote `tools/type_links.py`:
  - a fixed system prompt with the type vocabulary
  - one request per bio, with structured JSON output: types, exact quote, confidence
  - commands for counting, piloting and evaluating against Wikidata
- Exact count: **1,244 requests and 4.29M input tokens**. 1.6M of that is the repeated instructions, which can be cached.
- Revised estimate as a batch: Opus $21–39, Sonnet $11–18, Haiku $0.50–1. Proposed a pilot on all three models for about $4.

**Pete:** Just Sonnet and Haiku

**Claude:** Made the refusal fallback apply to Sonnet only, since Haiku doesn't support it. One Haiku request checked that everything worked; it typed Poe's links to Longfellow, Hawthorne and Irving well. Then ran 50 bios on each model in the background.

**Pete:** OK
**Pete:** I'll be gone for a while
**Pete:** Great

**Claude (results):** The pilot cost $0.63.

| | Haiku | Sonnet |
|---|---|---|
| Agreement with Wikidata | 51/67 | 52/67 |
| Agreement excluding "influenced by" and Lennon/Ono | 46/49 | 47/49 |
| Inexact quotes | 5 | 1 |
| Output tokens | 4× Sonnet's | — |

- The two models agreed on 88% of links. Sonnet's judgements were a little more nuanced, though both made some errors.
- Projected batch costs: Sonnet about $8–10, Haiku about $1.
- Proposed tightening the friend/acquaintance/colleague guidance, re-running the pilot, then running the full batch on Sonnet.

### Refining the instructions

**Pete:** I think merge "has met" into "acquaintance"  - I'd say err on the side of acquaintance for friend or colleague but highlight any possible discrpancy with Nat's material

**Claude:**
- **Changes:**
  - removed "has met"
  - made acquaintance the default when unsure
  - "mixed with a group including…" now supports acquaintance only
  - paid lessons count as teaching
  - interviews aren't portraits
  - added a `discrepancy` field for anything that doesn't fit Nat's record
  - prompt version 2
- **Re-run:** Sonnet pilot, $0.62. Acquaintance rose from 37 to 123, friend fell from 77 to 60 and colleague from 53 to 42. No inexact quotes.
- **Flags:** 44 discrepancies. Many were useful: Poe and Longfellow never met, Beckett and O'Casey only corresponded, several surname-only names were ambiguous, and Keats's and Wordsworth's bios disagree about who introduced them. About a quarter were noise.
- **Proposed:** categorising the flags, then running the full batch for about $9–11.

**Pete:** Submit to Sonnet as a batch with the categories you identified

**Claude:**
- **Changes:** added `discrepancy_type` (never_met, contradiction, ambiguous_name, dates, not_mentioned, other, none), batch `submit` and `collect` commands, and a `sheet` command for the review CSV. Prompt version 3.
- **Test:** one request cost $0.02. It also spotted that Henry Chopin and Henri Chopin are probably duplicates.
- **Submitted:** batch `msgbatch_01SHsF48SFVSxvs6aFrPXDeA`, 1,244 requests, with a check every five minutes in the background.

**Pete:** Great - I'll leave you to it

## 20 October 2026

**Claude (results):** The batch ended at 00:21. All 1,244 requests succeeded, and it cost **$9.74**.

- **Failures:** 2 requests ran out of output space and 1 was refused. 104 links were missing from otherwise good answers, and 1 ID was misspelled (`jacques-derida`).
- **Repair:** added a `repair` command that re-runs only the missing links directly, with more output space and the refusal fallback. All 111 were typed, for $0.20.
- **Wikidata:** 80% agreement, leaving out "influenced by". Only 17 of 801 directional types that Wikidata can check were reversed.
- **Birth years:** a check found 112 links where a teacher or parent was born more than five years after the pupil or child. Most are simply reversed: Boswell given as Johnson's teacher, William James as Agassiz's. Some reveal a wrong-person link: Bewick's pupil William Harvey is linked to the 1578-born physician. These are flagged in an `automatic_check` column, not flipped.
- **Flags:** never met 118, contradiction 187, ambiguous name 537, dates 165, other 529, not mentioned 2,886.
- **Outputs:** `data/link-types/review-run-v3-claude-sonnet-5-5-medium.csv` (12,401 lines, including the header), and the link-typing steps added to `tools/README.md`. Total API spend about $11.20; about $8.80 of credit left.

**Pete:** /log-session

**Claude:** Wrote this transcript and the summary in `repos/wkw/_sessions/`.

---

## 20 October 2026 (evening): instructions for Nat

This part came later in a Claude Code session that was mostly about other repositories.

**Pete:** I'd also like you to write some brief instructions for Nat about how to use the csv generated in the who know whom work last night, alond with a little background on how the data was reconciled and what the intended outcome is

**Claude:** Read this session's notes, `tools/type_links.py` (the types, the prompt and the sheet's columns and sort order) and the CSV. The CSV is the link-type review sheet, `review-run-v3-claude-sonnet-5-5-medium.csv`. "Reconciled" was taken to mean the clean-up and Wikidata matching, as Pete used it on 19 October. Counted the rows in each part of the sheet:

| Rows | What they are | Count |
|---|---|---|
| 2–113 | Failed the birth-year check | 112 |
| 114–1620 | Flagged by the model (never met, contradiction, ambiguous name, dates, other) | 1,507 |
| 1621–4505 | Neither biography mentions the other person | 2,885 |
| 4506–12401 | Nothing flagged, least certain first | 7,897 |

Nothing had been agreed about what Nat should write in the `decision` column, so Claude proposed `ok`, the corrected types, `reverse`, `wrong person` or `remove`, with blank meaning not reviewed. Pete's draft email (`email-2026-10-20.txt`) ended by introducing the CSV, so rather than edit it, Claude wrote the section to follow it in `email-2026-10-20-csv.txt`: how the data was reconciled, the columns, how to fill it in, the types, and what it's for.

**Pete (while Claude was working):** I've added some text the the email now

**Claude:** The saved draft still ended at the same place, so the section still followed on from it.

**Pete:** Is relationships and extension to foaf

**Claude:** Yes, in effect. RELATIONSHIP (Ian Davis and Eric Vitiello, 2004) is a separate vocabulary built on FOAF: each of its properties is defined as `rdfs:subPropertyOf foaf:knows`, between two `foaf:Person`s. So a typed link is still a `foaf:knows` link, and queries can ask for everyone someone knew or only the people they taught. The `wkw:` terms should be declared the same way when the typed links go into the RDF.

**Pete:** I've renamed it to readme.txt in the link-types folder - can you add this detail in there?

**Claude:** Added the explanation to `data/link-types/readme.txt`, including the `wkw:` types (with their reverse forms) that will be defined the same way.

**Pete:** and convert it to markdown

**Claude:** Wrote `data/link-types/readme.md` with headings, tables for the columns and the types, and links, and deleted `readme.txt`. The FOAF paragraph had been inserted in the middle of the paragraph about the AI model, which made "It was told to use only what your biographies say" read as if it were about the vocabulary, so it became its own paragraph.

**Pete:** Great - I'll send this along with the CSV when I've fionished writing the email

**Claude:** Mentioned that the tables would show as raw `|` characters in a plain text editor, and offered a PDF or HTML version.

**Pete:** He'll see this as a challenge and will rise to solving it

**Pete:** Please update the sessions files in wkw

**Claude:** Added this section to the transcript and a matching one to the summary.

---

# 3 November 2026: corrections, Wikidata, and the Jekyll site

**Participants:** Pete (user), Claude (assistant)

Pete's messages are quoted in full; Claude's replies and work are condensed. The same session also worked on minus20's slider, which is recorded in that repository and left out here. Nat's email is kept out of git, so it is summarised, not quoted.

## Nat's reply

**Pete:** I've heard back from the artists about the wkw data and relationship ontolology, and the judgement was harsh. Nat wants to drop the idea of using a vocabulary for relationships and stick to core FOAF. I'd still like to sort out any potential errors and add data from wikidata where its missing though

**Claude:** Read the previous session's notes and the scripts, and measured the gaps: about 1,960 people had no birth year and about 2,000 no birthplace, and Wikidata had one for most of them, but nearly all through medium-confidence matches resting only on a name and a lifetime. So before borrowing anything:

- **Impossible acquaintances:** checked every link for lifetimes that didn't overlap. Found Bewick linked to William Harvey the physician (his pupil was Harvey the engraver), Magnol linked to Antoine-Laurent de Jussieu (born after Magnol died; his pupil was Antoine de Jussieu), and four links between people who never overlapped. Two of those come from sentences in Nat's bios: Hill's friendship with Price, and Fanny Mendelssohn meeting Massenet in Italy.
- **Duplicates:** checked the 36 groups Wikidata had found. All were the same person; so was Henry/Henri Chopin, whose only link is Brion Gysin.
- **Dates:** fixed the 13 clear typos where Wikidata agreed, and left 7 where WKW is right or sources disagree.
- **`data/corrections.csv`:** all of these went into it, one row per correction with its reason, applied by `export_wp.py`. Each person's record lists its corrections.
- **Corroboration:** added a step to `wikidata.py`. A search match counts only if Wikidata or English Wikipedia connects the person to someone WKW says they knew. Fetching the Wikipedia links took about half an hour.

Nat's reply was then added to the email file. Nat had read the first ten rows of the sheet, found the relationship types and the "contradictions" based on them wrong, and decided against classifying relationships; Nat also resists a definitive list of professions, but saw a use for catching obvious slips against outside sources. So Claude borrowed no occupations from Wikidata.

**Pete:** I'm afraid he forgot to atach it!

**Claude:** Went ahead without the Word document. Results:

- 3,416 people after merging.
- 1,383 of 1,731 uncertain matches corroborated; the rest became `skos:closeMatch`.
- `supplement.ttl` fills dates for 1,462 people, so 2,873 now have dates.
- Spot checks of the corroborated matches all looked right.
- The README now records the relationship typing as dropped.

## Git

**Pete:** I've made wkw into a git repo and pushed the gitignore and sessions files. WHen you say data from before the changes, do you mean the original data from the wordpress site?

**Claude:** No: the copy was the cleaned data from October, before this session's changes. The WordPress data is the dump in `_dump/`, which only gets read. Suggested committing the October state first and the changes on top, so the corrections show as a diff, and noted that the October scripts would need this session's edits reversing by hand.

**Pete:** Can you reverse the edits for the commit, keep a scratchpad copy in data and do the two separate commits please?

**Claude:** Saved this session's state, reversed the edits to the three scripts and the README, and checked them by re-running them from the dump. They reproduced the October data, except that the order of some people's professions had varied between runs. Committed the October state with the scratchpad copy as `data/` (`d1e8b55`), then restored this session's work and committed it (`2c88200`). Checked that no API key or secrets were included.

## The Jekyll site

**Pete:** I'd like this to be a jekyll site, with the same pages and design as the wordpress site, plus the visualisation, and in browser sparql engine

**Claude:** Ran the original WordPress site locally: the dump's install and database in containers, with a fresh `wp-config.php` and WordPress's rewrite rules, as the dump has no `.htaccess`. Screenshotted and read its pages. Findings:

- The design comes from GeneratePress, GP Premium and the WKW child theme, plus CSS WordPress writes inline (the Customizer's colours, and the word cloud background image).
- Names link to `/types/<profession>/`; profession pages show ten people each.
- Acquaintances were listed in Nat's order, which the export had been sorting. Changed the export to keep it.
- The names list was meant to be alphabetical, but names without a sort key came first.
- The d3 graph in `wkw.js` had never been attached to a page.

Built `docs/` on a new branch, `jekyll-site`:

- **Assets:** the theme's stylesheets, scripts, fonts and images, and the inline CSS.
- **Layouts:** taken from WordPress's rendered HTML.
- **`tools/build_site.py`:** generates the data, the name and profession pages, and the files search, graph and SPARQL load.
- **`tools/import_pages.py`:** copied the ordinary pages from the running WordPress site, with their links rewritten.
- **Search:** runs in the browser.
- **The graph:** ported to d3 v7, with the static data in place of the WordPress API.
- **SPARQL:** Oxigraph in a worker, with twelve examples, each tested with Oxigraph in Python first. One example turned up James Rosenquist born in 1547: Wikidata's error. The supplement now skips borrowed dates that give an impossible lifespan.

Comparing screenshots with WordPress:

- **CSS order:** bundling the inline CSS had moved a rule ahead of the file it overrides, which broke the phone menu. The CSS now loads in WordPress's order.
- **Curly quotes:** WordPress showed bios and titles with curly quotes (`wptexturize`); added the same conversion.
- **Result:** 37 of 52 sampled pages then matched pixel for pixel below the menu, and the rest differed only by corrected data.
- **Links:** every internal link on 1,694 pages works.

## Field, network and query

**Pete:** Can you change graph to field and sparql to query. You also mentioned a version of the graph view whch could include all names and use webGL - it would be great to see how that operates

**Claude:** Renamed the pages, URLs and scripts (`/field/`, `/query/`), and moved the bio panel into a shared script. Built the whole-network view:

- **Libraries:** sigma.js with graphology's ForceAtlas2, bundled with esbuild (`tools/field-bundle/`). Sigma 4 was tried first, but its new styling API is too recent, so it uses sigma 3.
- **Layout:** the first version tangled into a ball. Offline tests with Node showed that even 2,000 rounds of ForceAtlas2 couldn't unfold it from a random start. Starting everyone at their estimated birth year, with low gravity, opened it into two halves joined by a bridge, roughly earlier centuries and the 20th century.
- **Lines:** sigma ignored transparency in line colours, so the lines are a solid colour already mixed with the background.

**Pete:** Can you call the view of all names "network"

**Claude:** Moved it to `/network/` with a menu item after "field". Committed (`8b39731`).

## Pages directory

**Pete:** Can you arrange the pages in a pages directory and use permalinks to get the number of subfolders down?

**Claude:** Moved every page into `docs/pages/` as a single file with a `permalink`: `pages/names/<id>.html`, `pages/types/<profession>-2.html` and so on, instead of more than 1,700 folders. `build_site.py` and `import_pages.py` now write there. Checked the result two ways:

- All 1,695 URLs are the same as before.
- The previous commit, built separately, is byte-for-byte identical to the new build.

## Session notes

**Pete:** I'll push the branch and do a PR in GitHub for it to merge into main. Can you update the sessions files for wkw?

**Claude:** Added this session to `summary.md` and `transcript.md`.
