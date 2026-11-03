"""
Generate the Jekyll site's data and pages from the cleaned data.

Reads data/wkw.json and data/rdf/*.ttl and writes, in docs/:

  _data/people.json        every person by id: name, whether they have a page, and for those
                           that do, their professions, dates, other names, sources, the people
                           they knew (in Nat's order) and their bio as HTML
  _data/names.json         every person's id in alphabetical order, for the list of names
  _data/latest.json        the three people most recently written up, for the home page
  pages/names.html         the list of names (/names/)
  pages/names/<id>.html    a page for each person with a bio, at /names/<id>/ (people without
                           one, the stubs, never had a page)
  pages/types/<profession>.html, <profession>-2.html ...
                           each profession's people, ten to a page as WordPress showed them, at
                           /types/<profession>/, /types/<profession>/page/2/ ...
  assets/data/graph.json   the network, for the field and network pages
  assets/data/search.json  names and bios, for the search page
  assets/data/*.ttl        the RDF, for the query page

Everything it writes is generated, so it is safe to delete and re-run. The pages' look is in
docs/_layouts and docs/_includes.

Usage: python3 -I tools/build_site.py
"""
import html
import json
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_wp import slugify  # noqa: E402  (WordPress's term slugs)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
PAGES = DOCS / "pages"   # every page is a file here, its URL set by its permalink
PER_PAGE = 10        # WordPress's posts per page on the profession archives
EXCERPT_WORDS = 30   # GeneratePress's excerpt length on the home page and in search results


def fold(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


def sort_key(p):
    """WKW's sort key ('Babbage, Charles'); for the many stubs without one, family name first.
    A few sort keys are just the name ('Howard Florey'), which would sort them by first name."""
    key = p["sort_key"]
    if key and not (" " in key and "," not in key):
        return fold(key)
    if p["family_name"] and p["family_name"] != p["name"]:
        return fold(f"{p['family_name']}, {p['given_name'] or ''}")
    words = re.sub(r"\s*\([^)]*\)", "", p["name"]).split()  # 'Sonny Boy Williamson (II)'
    return fold(" ".join(words[-1:] + words[:-1]))


def texturize(s):
    """The common part of WordPress's wptexturize, which it applied to bios and titles when it
    showed them: curly quotes and apostrophes, en and em dashes, and ellipses."""
    s = s.replace("...", "\u2026").replace(" -- ", " \u2014 ").replace("--", "\u2013").replace(" - ", " \u2013 ")
    s = re.sub(r"(?<=\w)'(?=\w)", "\u2019", s)                     # Newton's, O'Faolain
    s = re.sub(r"(^|(?<=[\s(\[{\u2014\u2013-]))'(?=\d\ds)", "\u2019", s)  # the '60s
    s = re.sub(r"(^|(?<=[\s(\[{\u2014\u2013\"-]))'", "\u2018", s)    # opening
    s = s.replace("'", "\u2019")                                     # closing, and the rest
    s = re.sub(r'(^|(?<=[\s(\[{\u2014\u2013\u2018-]))"', "\u201c", s)
    return s.replace('"', "\u201d")


def paragraphs(text):
    return "".join(f"<p>{html.escape(texturize(par), quote=False)}</p>\n" for par in text.split("\n\n"))


def excerpt(text, words=EXCERPT_WORDS):
    w = text.split()
    return texturize(" ".join(w[:words])) + (" ..." if len(w) > words else "")


def birth_years(people):
    """Roughly when everyone was born: WKW's year, else 60 years before they died, else Wikidata's
    year for a trusted match, else the median of the people they knew (spread a few times)."""
    wikidata = json.loads((DATA / "wikidata.json").read_text()) if (DATA / "wikidata.json").exists() else {}
    years = {}
    for p in people:
        y = (p["birth"] or {}).get("year")
        if y is None and (p["death"] or {}).get("year"):
            y = p["death"]["year"] - 60
        w = wikidata.get(p["id"], {})
        if y is None and w.get("qid") and w["wikidata"]["birth"] and (
                w["confidence"] in ("high", "checked") or w.get("corroborated_by")):
            y = min(e["year"] for e in w["wikidata"]["birth"])
        if y is not None:
            years[p["id"]] = y
    for _ in range(5):
        guesses = {}
        for p in people:
            known = sorted(years[k] for k in p["knows"] if k in years)
            if p["id"] not in years and known:
                guesses[p["id"]] = known[len(known) // 2]
        years.update(guesses)
    return years


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def front_matter(**values):
    return "---\n" + "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in values.items()) + "---\n"


def pager(base, page, pages):
    """WordPress's paginate_links (one page at each end, two either side of the current one)."""
    def link(n):
        return "{{ '" + base + ("" if n == 1 else f"page/{n}/") + "' | relative_url }}"
    out = ['<nav id="nav-below" class="paging-navigation" aria-label="Archive Page">']
    if page < pages:
        out.append('<div class="nav-previous"><span class="prev" title="Previous">'
                   f'<a href="{link(page + 1)}" >Older posts</a></span></div>')
    if page > 1:
        out.append('<div class="nav-next"><span class="next" title="Next">'
                   f'<a href="{link(page - 1)}" >Newer posts</a></span></div>')
    out.append('<div class="nav-links">')
    if page > 1:
        out.append(f'<a class="prev page-numbers" href="{link(page - 1)}"><span aria-hidden="true">&larr;</span> Previous</a>')
    dots = False
    for n in range(1, pages + 1):
        if n == page:
            out.append(f'<span aria-current="page" class="page-numbers current"><span class="screen-reader-text">Page</span>{n}</span>')
            dots = False
        elif n <= 1 or n > pages - 1 or abs(n - page) <= 2:
            out.append(f'<a class="page-numbers" href="{link(n)}"><span class="screen-reader-text">Page</span>{n}</a>')
            dots = False
        elif not dots:
            out.append('<span class="page-numbers dots">&hellip;</span>')
            dots = True
    if page < pages:
        out.append(f'<a class="next page-numbers" href="{link(page + 1)}">Next <span aria-hidden="true">&rarr;</span></a>')
    out.append("</div></nav>")
    return "\n".join(out)


def main():
    people = json.loads((DATA / "wkw.json").read_text())
    by_id = {p["id"]: p for p in people}
    bios = [p for p in people if p["status"] == "bio"]

    for d in ("names", "types"):
        shutil.rmtree(PAGES / d, ignore_errors=True)

    # professions, grouped by slug ('film director' and 'film-director' were two terms)
    prof_people = defaultdict(list)
    prof_names = defaultdict(lambda: defaultdict(int))
    for p in sorted(bios, key=lambda p: p["created"] or "", reverse=True):  # newest first, as WordPress
        for prof in p["professions"]:
            prof_people[slugify(prof)].append(p["id"])
            prof_names[slugify(prof)][prof] += 1

    data = {}
    for p in people:
        entry = {"name": p["name"]}
        if p["status"] == "bio":
            entry.update({
                "page": True,
                "title": texturize(p["name"]),
                "alt": "; ".join(a.strip() for a in p["alt_name"].split(";")) if p["alt_name"] else None,
                "professions": [[prof, slugify(prof)] for prof in p["professions"]],
                "dates": p["dates_text"],
                "sources": [[s["url"], s["text"] or s["url"]] for s in p["sources"]],
                "knew": p["knows"],
                "bio": paragraphs(p["bio"]),
            })
        data[p["id"]] = entry
    write(DOCS / "_data" / "people.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    names = sorted(people, key=sort_key)
    write(DOCS / "_data" / "names.json", json.dumps([p["id"] for p in names]))
    latest = sorted(bios, key=lambda p: p["created"] or "", reverse=True)[:3]
    write(DOCS / "_data" / "latest.json",
          json.dumps([{"id": p["id"], "excerpt": excerpt(p["bio"])} for p in latest], ensure_ascii=False))

    write(PAGES / "names.html",
          front_matter(layout="names", title="Names", permalink="/names/",
                       body_class="archive post-type-archive post-type-archive-wkwname"))
    for p in bios:
        write(PAGES / "names" / f"{p['id']}.html",
              front_matter(layout="name", title=p["name"], person=p["id"], permalink=f"/names/{p['id']}/",
                           body_class=f"wp-singular wkwname-template-default single single-wkwname {p['id']} wkwname"))

    for slug, ids in prof_people.items():
        label = max(prof_names[slug].items(), key=lambda kv: kv[1])[0]
        pages = (len(ids) + PER_PAGE - 1) // PER_PAGE
        base = f"/types/{slug}/"
        for n in range(1, pages + 1):
            path = PAGES / "types" / (f"{slug}.html" if n == 1 else f"{slug}-{n}.html")
            write(path, front_matter(layout="profession", title=label + (f" – Page {n}" if n > 1 else ""),
                                     permalink=base if n == 1 else f"{base}page/{n}/",
                                     profession=label, people=ids[(n - 1) * PER_PAGE:n * PER_PAGE],
                                     body_class=f"archive tax-wkwcategory term-{slug}" + (" paged" if n > 1 else ""))
                  + pager(base, n, pages) + "\n")

    # the network for the field and network pages: nodes are [id, name, has a page, year], links
    # are index pairs. The year is roughly when they were born, to start the network's layout
    index = {p["id"]: i for i, p in enumerate(people)}
    years = birth_years(people)
    graph = {"nodes": [[p["id"], p["name"], p["status"] == "bio", years.get(p["id"])] for p in people],
             "links": [[index[p["id"]], index[k]] for p in people for k in p["knows"] if p["id"] < k]}
    write(DOCS / "assets" / "data" / "graph.json", json.dumps(graph, ensure_ascii=False, separators=(",", ":")))

    # search: WordPress searched the published names' titles and text
    search = [[p["id"], data[p["id"]]["title"], data[p["id"]]["alt"] or "", data[p["id"]]["professions"],
               p["dates_text"] or "", texturize(p["bio"])] for p in bios]
    write(DOCS / "assets" / "data" / "search.json", json.dumps(search, ensure_ascii=False, separators=(",", ":")))

    for f in ("wkw.ttl", "supplement.ttl", "wikidata.ttl"):
        shutil.copyfile(DATA / "rdf" / f, DOCS / "assets" / "data" / f)

    print(f"{len(bios)} name pages, {len(prof_people)} professions, {len(people)} people in the list, "
          f"{len(graph['links'])} links in the graph")


if __name__ == "__main__":
    main()
