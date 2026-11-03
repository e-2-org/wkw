# Who Knew Whom

*Who Knew Whom* is Nat Goodden's research into who knew whom among more than 3,000 figures in the arts and sciences: a short biography of each person, and links to everyone they knew. It began as a MediaWiki site and became a WordPress site at culturalcartography.net. This repository holds its data, cleaned up and published as linked data, and a static version of the site.

## The site

`docs/` is a Jekyll site for GitHub Pages, with the WordPress site's pages, URLs and design:

- **The same pages:** the home page with the latest additions, the list of names, a page for each person with a bio (people without one never had a page), each profession's people (`types/`), and the about pages and blog, copied from WordPress.
- **The same design:** the GeneratePress theme's and the WKW child theme's stylesheets, scripts, fonts (Handsome Pro, licensed for the website) and images.
- **Search** runs in the browser, through the names and bios, as WordPress's search did.
- **The graph** (`graph/`) is the force-directed graph the WKW theme had started, finished: one person, the people they knew, and the people those people knew. Each person's page links to their graph.
- **SPARQL** (`sparql/`) runs queries over the linked data in the browser, with examples to start from.

`docs/_config.yml` says where everything is. Most of the site is generated from the data by `tools/build_site.py`; the pages copied from WordPress are edited in `docs/`.

To run it locally, use `bundle install` and then `bundle exec jekyll serve` from inside `docs/`. The site is then at http://localhost:4000/wkw/.

## The data

`data/` holds the data taken out of the WordPress database and cleaned up, matched with Wikidata, and published as RDF:

- `data/wkw.json` and `data/csv/`: everyone, with their dates, professions, bios, sources and the people they knew
- `data/rdf/wkw.ttl`: the same as linked data, using FOAF (`foaf:knows` for who knew whom) and schema.org
- `data/rdf/supplement.ttl`: dates and places Who Knew Whom doesn't give, from Wikidata
- `data/rdf/wikidata.ttl`: what Wikidata says about the same people
- `data/corrections.csv`: errors corrected in the data, such as duplicate records and mistyped years, each with the reason
- `data/reports/`: what the clean-up changed, and what still needs checking

`tools/` holds the scripts that do this; `tools/README.md` explains how to run them.

## Layout

The original WordPress and MediaWiki install and its database are in `_dump/`, which isn't in git because it contains passwords and users' details. Summaries and transcripts of the Claude Code sessions are in `_sessions/`.
