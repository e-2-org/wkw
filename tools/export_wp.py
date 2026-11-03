"""
Export Who Knew Whom names from the WordPress database into clean, standard data.

Reads the wkwname posts, their ACF fields and professions from a MariaDB copy of
ng_culturalcartography_net.sql, cleans them, and writes:

  data/wkw.json            every person as one cleaned record (the pipeline's working copy)
  data/csv/*.csv           the same data as spreadsheet-friendly tables
  data/reports/export.md   what the clean-up changed or couldn't resolve

The database is reached through WKW_DB_CMD (default: the wkw-db container that
tools/README.md describes), which must accept SQL on stdin.

Usage: python3 -I tools/export_wp.py
"""
import collections
import csv
import html
import json
import os
import re
import shlex
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB_CMD = os.environ.get(
    "WKW_DB_CMD", "docker exec -i wkw-db mariadb -uroot wkw --batch --raw --skip-column-names"
)


def query(sql):
    """Runs SQL that returns one JSON object per row; yields them as dicts."""
    out = subprocess.run(
        shlex.split(DB_CMD), input=sql, capture_output=True, text=True, check=True
    ).stdout
    for line in out.splitlines():
        if line.startswith("{"):
            yield json.loads(line)


def php_ids(value):
    """IDs from a PHP-serialised array of strings or integers, e.g. a:2:{i:0;s:4:"3634";i:1;i:3447;}"""
    if not value:
        return []
    return [int(s or i) for s, i in re.findall(r'(?:s:\d+:"(\d+)"|i:\d+;i:(\d+))', value)]


def clean_text(s):
    """Decodes entities, normalises Unicode and spaces."""
    if s is None:
        return ""
    s = html.unescape(s).replace("\u00a0", " ")
    s = unicodedata.normalize("NFC", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def slugify(s):
    """Like WordPress's sanitize_title: strip accents, lower case, hyphens."""
    s = unicodedata.normalize("NFKD", s.replace("ß", "ss").replace("ø", "o").replace("Ø", "O")
                              .replace("ł", "l").replace("Ł", "L").replace("æ", "ae"))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# One side of birth_death: optional circa, a year (or "unknown"/"?date"), optional (place)
SIDE = r"\s*(?P<{0}c>c\.?\s*)?(?P<{0}y>\d{{3,4}}(?:/\d{{1,2}})?|unknown|\?date)?\s*(?:\((?P<{0}p>(?:[^()]|\([^()]*\))*)\)+)?\s*"
DATES = re.compile("^" + SIDE.format("b") + r"(?:[–—-]" + SIDE.format("d") + r")?['\"]*$")


def parse_dates(raw):
    """Splits '1791 (London) – 1871 (London)' into birth and death parts. Returns (birth, death, ok)."""
    raw = clean_text(raw)
    if not raw:
        return None, None, True
    # repair a stray bracket, e.g. '1879 (Shanghai), China) -'
    fixed = re.sub(r"^\((\d[^()]*)\)$", r"\1", raw)  # '(1894 – 1986)'
    if fixed.count("(") < fixed.count(")"):
        fixed = re.sub(r"\(([^()]*)\),([^()]*)\)", r"(\1,\2)", raw)
    m = DATES.match(fixed)
    if not m:
        return None, None, False

    def side(k):
        year, place = m.group(k + "y"), m.group(k + "p")
        if not year and not place:
            return None
        d = {}
        if year and year[0].isdigit():
            d["year"] = int(year.split("/")[0])
            if "/" in year:
                d["year_note"] = year
        if m.group(k + "c"):
            d["circa"] = True
        place = clean_text(place)
        if place.startswith("?"):
            d["place_uncertain"] = True
            place = place[1:].strip()
        if place and "unknown" not in place:
            d["place"] = place
        return d or None

    return side("b"), side("d"), True


def norm_url(url):
    url = clean_text(url)
    url = re.sub(r"^http://", "https://", url)
    url = re.sub(r"^https://([a-z]+)\.m\.wikipedia\.org/", r"https://\1.wikipedia.org/", url)
    return url


def main():
    posts = {p["id"]: p for p in query("""
        SELECT JSON_OBJECT('id', ID, 'title', post_title, 'slug', post_name, 'status', post_status,
                           'bio', post_content, 'created', post_date, 'modified', post_modified)
        FROM wp_posts WHERE post_type = 'wkwname';""")}

    meta = collections.defaultdict(dict)
    for r in query("""
        SELECT DISTINCT JSON_OBJECT('id', m.post_id, 'k', m.meta_key, 'v', m.meta_value)
        FROM wp_postmeta m JOIN wp_posts p ON p.ID = m.post_id
        WHERE p.post_type = 'wkwname' AND m.meta_key NOT LIKE '\\_%';"""):
        meta[r["id"]][r["k"]] = r["v"]

    terms = {t["id"]: t for t in query("""
        SELECT JSON_OBJECT('id', t.term_id, 'name', t.name, 'slug', t.slug, 'parent', tt.parent)
        FROM wp_terms t JOIN wp_term_taxonomy tt USING (term_id) WHERE tt.taxonomy = 'wkwcategory';""")}
    post_terms = collections.defaultdict(list)
    for r in query("""
        SELECT JSON_OBJECT('id', r.object_id, 'term', tt.term_id)
        FROM wp_term_relationships r JOIN wp_term_taxonomy tt USING (term_taxonomy_id)
        WHERE tt.taxonomy = 'wkwcategory' ORDER BY r.object_id, r.term_order;"""):
        post_terms[r["id"]].append(r["term"])

    report = collections.defaultdict(list)

    # The Lucio Fontana draft is an empty record started in 2021; only names that were live are kept
    for pid, p in list(posts.items()):
        if p["status"] not in ("publish", "pending"):
            report["dropped"].append(f"{clean_text(p['title'])} (WordPress {pid}, status {p['status']})")
            del posts[pid]

    # a few records have an empty title but their name is in the first/last name fields
    for pid, p in posts.items():
        p["title"] = clean_text(p["title"])
        if not p["title"]:
            p["title"] = clean_text(f"{meta[pid].get('wkw_first_name', '')} {meta[pid].get('wkw_last_name', '')}")
            report["untitled"].append(f"{p['title']} (WordPress {pid})")

    # Duplicates: the 2018 import made a stub for every name, and some were added again by hand,
    # sometimes spelt without accents. Records whose names match once accents are removed are
    # merged into one, preferring a published record, then the one with the most links.
    canon = {}
    groups = collections.defaultdict(list)
    for pid, p in posts.items():
        groups[slugify(p["title"])].append(pid)
    for key, pids in groups.items():
        def rank(pid):
            p = posts[pid]
            accents = sum(1 for c in p["title"] if ord(c) > 127)
            return (p["status"] != "publish", -len(php_ids(meta[pid].get("wkw_linked_names"))),
                    -accents, pid)
        pids.sort(key=rank)
        for pid in pids:
            canon[pid] = pids[0]
        if len(pids) > 1:
            report["merged"].append(
                f"**{posts[pids[0]]['title']}** (WordPress {pids[0]}, {posts[pids[0]]['status']}) ← "
                + ", ".join(f"{posts[x]['title']} ({x}, {posts[x]['status']})" for x in pids[1:]))

    # slugs: published names keep theirs so old URLs still resolve; pending names never had one
    slugs, used = {}, set()
    for pid, p in sorted(posts.items(), key=lambda kv: (kv[1]["status"] != "publish", kv[0])):
        if canon[pid] != pid:
            continue
        base = p["slug"] or slugify(clean_text(p["title"]))
        slug, n = base, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        if slug != base:
            report["slug_clash"].append(f"{clean_text(p['title'])} → `{slug}`")
        used.add(slug)
        slugs[pid] = slug

    # links between names: make them symmetric, drop ones to missing posts or to oneself
    knows = collections.defaultdict(set)
    for pid in posts:
        for t in php_ids(meta[pid].get("wkw_linked_names")):
            if t not in posts:
                report["dangling"].append(f"{posts[pid]['title']} → WordPress {t}")
            elif canon[t] == canon[pid]:
                if t == pid:
                    report["self_link"].append(posts[pid]["title"])
            else:
                knows[canon[pid]].add(canon[t])
    one_way = sorted({(a, b) for a in knows for b in knows[a] if a not in knows[b]})
    for a, b in one_way:
        knows[b].add(a)
    report["one_way_count"] = len(one_way)

    people = []
    for pid, p in posts.items():
        if canon[pid] != pid:
            continue
        dupes = [x for x in posts if canon[x] == pid and x != pid]
        records = [pid] + dupes

        def field(key):
            """The first non-empty value of an ACF field across the merged records."""
            for x in records:
                v = clean_text(meta[x].get(key))
                if v:
                    return v
            return None

        # the spelling with the most accents, as duplicates were often typed without them
        name = max((posts[x]["title"] for x in records), key=lambda t: sum(ord(c) > 127 for c in t))
        dates_text = field("wkw_birth_death")
        birth, death, ok = parse_dates(dates_text)
        if not ok:
            report["dates_unparsed"].append(f"{name}: `{dates_text}`")

        sources, seen = [], set()
        for x in records:
            m = meta[x]
            n = int(m["wkw_name_links"]) if (m.get("wkw_name_links") or "").isdigit() else 0
            for i in range(n):
                url = norm_url(m.get(f"wkw_name_links_{i}_link_url"))
                if not url:
                    continue
                if url in seen:
                    report["duplicate_source"].append(f"{name}: {url}")
                    continue
                seen.add(url)
                sources.append({"url": url, "text": clean_text(m.get(f"wkw_name_links_{i}_link_text"))})

        # professions: the ordered ACF field where it exists, else the taxonomy terms
        professions = []
        for x in records:
            for t in php_ids(meta[x].get("professions_ordered")) or post_terms[x]:
                if t in terms and clean_text(terms[t]["name"]) not in professions:
                    professions.append(clean_text(terms[t]["name"]))

        bio = "\n\n".join(clean_text(par) for par in re.split(r"\n\s*\n", p["bio"] or "") if par.strip())
        disambiguation = {canon[t] for x in records
                          for t in php_ids(meta[x].get("wkw_disambiguation_names")) if t in posts}

        people.append({
            "id": slugs[pid],
            "name": name,
            "given_name": field("wkw_first_name"),
            "family_name": field("wkw_last_name"),
            "sort_key": field("wkw_sort_key"),
            "alt_name": field("wkw_aka_name"),
            "status": "bio" if p["status"] == "publish" else "stub",
            "dates_text": dates_text,
            "birth": birth,
            "death": death,
            "professions": professions,
            "bio": bio or None,
            "knows": sorted(slugs[t] for t in knows[pid]),
            "disambiguation": sorted(slugs[t] for t in disambiguation - {pid}),
            "sources": sources,
            "wordpress_ids": records,
            "mediawiki_id": field("wkw_wiki_id"),
            "created": min(posts[x]["created"] for x in records),
            "modified": max(posts[x]["modified"] for x in records),
        })

    people.sort(key=lambda x: (x["sort_key"] or x["name"]).casefold())
    by_name = collections.defaultdict(list)
    for x in people:
        by_name[x["name"].casefold()].append(x["id"])
    report["same_name"] = [", ".join(ids) for ids in by_name.values() if len(ids) > 1]
    report["unlinked"] = [x["name"] for x in people if not x["knows"]]
    report["stub_missing_sort"] = sum(1 for x in people if not x["sort_key"])

    DATA.mkdir(exist_ok=True)
    (DATA / "wkw.json").write_text(json.dumps(people, ensure_ascii=False, indent=1) + "\n")
    write_csvs(people)
    write_report(people, report, one_way, slugs)


def write_csvs(people):
    d = DATA / "csv"
    d.mkdir(exist_ok=True)

    def w(name, header, rows):
        with open(d / name, "w", newline="", encoding="utf-8") as f:
            out = csv.writer(f)
            out.writerow(header)
            out.writerows(rows)

    w("people.csv",
      ["id", "name", "given_name", "family_name", "sort_key", "alt_name", "status", "dates_text",
       "birth_year", "birth_circa", "birth_place", "death_year", "death_circa", "death_place",
       "professions", "bio"],
      [[x["id"], x["name"], x["given_name"], x["family_name"], x["sort_key"], x["alt_name"], x["status"],
        x["dates_text"],
        *[(x[k] or {}).get(f) for k in ("birth", "death") for f in ("year", "circa", "place")],
        "; ".join(x["professions"]), x["bio"]] for x in people])
    w("knows.csv", ["person", "knew"],
      [[x["id"], k] for x in people for k in x["knows"] if x["id"] < k])
    w("sources.csv", ["person", "url", "text"],
      [[x["id"], s["url"], s["text"]] for x in people for s in x["sources"]])
    w("disambiguation.csv", ["person", "see_also"],
      [[x["id"], k] for x in people for k in x["disambiguation"]])


def write_report(people, r, one_way, slugs):
    bios = sum(1 for x in people if x["status"] == "bio")
    edges = sum(len(x["knows"]) for x in people) // 2
    dated = sum(1 for x in people if x["birth"] or x["death"])

    def section(title, items, note=""):
        out = [f"## {title} ({len(items)})", ""]
        if note:
            out += [note, ""]
        out += [f"- {i}" for i in items] if items else ["None."]
        return out + [""]

    lines = [
        "# Export from WordPress", "",
        f"- **People:** {len(people)} ({bios} with a bio, {len(people) - bios} stubs: people linked to "
        "but not yet written up)",
        f"- **Acquaintanceships:** {edges}",
        f"- **With dates:** {dated}",
        f"- **Sources:** {sum(len(x['sources']) for x in people)} links to outside sources",
        "",
        f"## One-way links made two-way ({r['one_way_count']})", "",
        "WordPress's save hook keeps links two-way; this checks that it did. Any found are listed in "
        "`one-way-links.csv` and now run both ways.", "",
    ]
    lines += section("Links to deleted names, dropped", r["dangling"])
    lines += section("Links to self, dropped", r["self_link"])
    lines += section("Records dropped", r["dropped"])
    lines += section("Records with no title, named from their first and last names", r["untitled"])
    lines += section("Duplicate records merged", r["merged"],
                     "Names that match once accents and case are ignored. The first record is kept and the "
                     "others' links, sources, dates and professions are added to it.")
    lines += section("Dates that couldn't be parsed", r["dates_unparsed"],
                     "`dates_text` keeps the original; birth and death are left empty.")
    lines += section("Repeated source links, dropped", r["duplicate_source"])
    lines += section("Different people with the same name", r["same_name"],
                     "Check whether these are duplicates or genuinely different people.")
    lines += section("Slugs that clashed and were numbered", r["slug_clash"])
    lines += section("People with no links", r["unlinked"])
    (DATA / "reports").mkdir(exist_ok=True)
    (DATA / "reports" / "export.md").write_text("\n".join(lines))
    with open(DATA / "reports" / "one-way-links.csv", "w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["linked_from", "linked_to_but_not_back"])
        out.writerows([[slugs[a], slugs[b]] for a, b in one_way])


if __name__ == "__main__":
    main()
