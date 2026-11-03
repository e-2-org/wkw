"""
Reconcile Who Knew Whom people with Wikidata, and fetch what Wikidata knows about them.

Reads data/wkw.json (from export_wp.py) and writes:

  data/wikidata.json          per person: the Wikidata item, how it was found, how sure the match
                              is, and the item's dates, places, occupations, identifiers and any
                              relationships to other WKW people
  data/reports/wikidata.md    summary, disagreements with WKW's own data, and unmatched people
  data/reports/wikidata-review.csv   matches and candidates for a person to check

Matching, most reliable first:

  1. wikipedia  a Wikipedia article in the person's sources, resolved to its Wikidata item
  2. search     Wikidata's name search plus an English Wikipedia page with the same title,
                restricted to humans and scored on birth and death years. Candidates who weren't
                alive at the same time as anyone they are said to have known are rejected.

Medium and low search matches are then checked against the people WKW says they knew: a match is
corroborated if Wikidata records a relationship with one of them, or either person's English
Wikipedia article links to the other's. build_rdf.py only borrows Wikidata's facts for people
whose match is high, checked or corroborated.

Confirmed or corrected matches can be recorded in data/wikidata-overrides.csv
(columns: person, qid, note); a qid of "none" means the person isn't on Wikidata.

HTTP responses are cached in tools/.cache, so re-running is cheap.

Usage: python3 -I tools/wikidata.py
"""
import csv
import hashlib
import json
import math
import re
import time
import unicodedata
import urllib.parse
from collections import defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = Path(__file__).resolve().parent / ".cache"
UA = "WhoKnewWhom-reconcile/0.1 (https://github.com/e-2-org; data clean-up for culturalcartography.net)"
WDQS = "https://query.wikidata.org/sparql"
WD_API = "https://www.wikidata.org/w/api.php"

session = requests.Session()
session.headers["User-Agent"] = UA


def cached(kind, key, fetch):
    """Returns fetch()'s JSON, cached on disk under kind/sha1(key)."""
    path = CACHE / kind / (hashlib.sha1(key.encode()).hexdigest() + ".json")
    if path.exists():
        return json.loads(path.read_text())
    for attempt in range(5):
        try:
            result = fetch()
            break
        except requests.RequestException as e:
            wait = 5 * (attempt + 1)
            print(f"  {kind}: {e}; retrying in {wait}s")
            time.sleep(wait)
    else:
        raise RuntimeError(f"{kind} request failed: {key[:200]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result))
    time.sleep(0.2)
    return result


def get_json(url, params):
    r = session.get(url, params=params, timeout=60)
    if r.status_code == 429:
        time.sleep(int(r.headers.get("Retry-After", 30)))
        r.raise_for_status()
    r.raise_for_status()
    return r.json()


def sparql(query):
    def fetch():
        r = session.post(WDQS, data={"query": query, "format": "json"}, timeout=120)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 60)))
        r.raise_for_status()
        return r.json()["results"]["bindings"]
    return cached("sparql", query, fetch)


def fold(s):
    """Lower case without accents or punctuation, for comparing names."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def qid(uri):
    return uri.rsplit("/", 1)[-1]


# --- Stage 1: Wikipedia links in the sources --------------------------------------------------

def wikipedia_title(url):
    """(lang, title) for a Wikipedia article URL, or None."""
    m = re.match(r"https?://([a-z\-]+)\.wikipedia\.org/(?:wiki/([^?#]+)|w/index\.php\?(.*))", url)
    if not m:
        return None
    lang, path, query = m.groups()
    if path:
        title = urllib.parse.unquote(path)
    else:
        title = urllib.parse.parse_qs(query).get("title", [""])[0]
    title = title.replace("_", " ").strip()
    return (lang, title) if title else None


def wikipedia_items(lang, titles):
    """Maps titles to {qid, disambiguation} via the Wikipedia API, following redirects."""
    out = {}
    titles = sorted(set(titles))
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        params = {"action": "query", "format": "json", "formatversion": 2, "redirects": 1,
                  "prop": "pageprops", "ppprop": "wikibase_item|disambiguation",
                  "titles": "|".join(batch)}
        api = f"https://{lang}.wikipedia.org/w/api.php"
        data = cached("wikipedia", f"{lang}|{params['titles']}", lambda: get_json(api, params))
        q = data.get("query", {})
        rename = {}
        for step in ("normalized", "redirects"):
            for n in q.get(step, []):
                rename[n["from"]] = n["to"]
        pages = {p["title"]: p for p in q.get("pages", [])}
        for t in batch:
            final = t
            while final in rename:
                final = rename[final]
            p = pages.get(final)
            if p and "pageprops" in p and "wikibase_item" in p["pageprops"]:
                out[t] = {"qid": p["pageprops"]["wikibase_item"],
                          "disambiguation": "disambiguation" in p["pageprops"], "title": final}
    return out


# --- Wikidata details --------------------------------------------------------------------------

def year_of(binding):
    """Year from a WDQS time value such as '-0384-01-01T00:00:00Z'."""
    m = re.match(r"(-?)(\d+)-", binding["value"])
    return -int(m.group(2)) if m.group(1) else int(m.group(2))


def fetch_details(qids):
    """Fetches the facts the reconciliation and enrichment need, for a set of items."""
    qids = sorted(set(qids))
    d = {q: {"qid": q, "label": None, "description": None, "human": False, "sitelinks": 0,
             "aliases": [], "birth": [], "death": [], "birth_place": [], "death_place": [],
             "occupations": [], "image": None, "enwiki": None, "ids": {}} for q in qids}
    for i in range(0, len(qids), 250):
        values = " ".join(f"wd:{q}" for q in qids[i:i + 250])
        for b in sparql(f"""
            SELECT ?item ?label ?desc ?links ?human ?image ?enwiki WHERE {{
              VALUES ?item {{ {values} }}
              OPTIONAL {{ ?item rdfs:label ?label FILTER(lang(?label) = "en") }}
              OPTIONAL {{ ?item rdfs:label ?label FILTER(lang(?label) = "mul") }}
              OPTIONAL {{ ?item schema:description ?desc FILTER(lang(?desc) = "en") }}
              OPTIONAL {{ ?item wikibase:sitelinks ?links }}
              BIND(EXISTS {{ ?item wdt:P31 wd:Q5 }} AS ?human)
              OPTIONAL {{ ?item wdt:P18 ?image }}
              OPTIONAL {{ ?enwiki schema:about ?item; schema:isPartOf <https://en.wikipedia.org/> }}
            }}"""):
            x = d[qid(b["item"]["value"])]
            x["label"] = x["label"] or b.get("label", {}).get("value")
            x["description"] = b.get("desc", {}).get("value")
            x["sitelinks"] = int(b.get("links", {}).get("value", 0))
            x["human"] = b["human"]["value"] == "true"
            x["image"] = x["image"] or b.get("image", {}).get("value")
            x["enwiki"] = b.get("enwiki", {}).get("value")
        for b in sparql(f"""
            SELECT ?item ?alias WHERE {{
              VALUES ?item {{ {values} }}
              ?item skos:altLabel ?alias FILTER(lang(?alias) IN ("en", "mul", "fr", "de", "it", "es"))
            }}"""):
            d[qid(b["item"]["value"])]["aliases"].append(b["alias"]["value"])
        for prop, key in (("P569", "birth"), ("P570", "death")):
            for b in sparql(f"""
                SELECT ?item ?t ?precision WHERE {{
                  VALUES ?item {{ {values} }}
                  ?item p:{prop} ?st. ?st wikibase:rank ?rank FILTER(?rank != wikibase:DeprecatedRank)
                  ?st psv:{prop} [ wikibase:timeValue ?t; wikibase:timePrecision ?precision ].
                }}"""):
                prec = int(b["precision"]["value"])
                entry = {"year": year_of(b["t"]), "precision": prec}
                if prec >= 11:
                    entry["date"] = b["t"]["value"][:10]
                if entry not in d[qid(b["item"]["value"])][key]:
                    d[qid(b["item"]["value"])][key].append(entry)
        for prop, key in (("P19", "birth_place"), ("P20", "death_place"), ("P106", "occupations")):
            for b in sparql(f"""
                SELECT ?item ?v ?vLabel ?coord WHERE {{
                  VALUES ?item {{ {values} }}
                  ?item wdt:{prop} ?v.
                  OPTIONAL {{ ?v wdt:P625 ?coord }}
                  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul,fr,de". }}
                }}"""):
                entry = {"qid": qid(b["v"]["value"]), "label": b.get("vLabel", {}).get("value")}
                if "coord" in b:
                    lon, lat = re.findall(r"-?[\d.]+", b["coord"]["value"])[:2]
                    entry["lat"], entry["lon"] = float(lat), float(lon)
                lst = d[qid(b["item"]["value"])][key]
                if not any(e["qid"] == entry["qid"] for e in lst):
                    lst.append(entry)
        for b in sparql(f"""
            SELECT ?item ?viaf ?ulan ?isni ?lc ?gnd ?bnf WHERE {{
              VALUES ?item {{ {values} }}
              OPTIONAL {{ ?item wdt:P214 ?viaf }} OPTIONAL {{ ?item wdt:P245 ?ulan }}
              OPTIONAL {{ ?item wdt:P213 ?isni }} OPTIONAL {{ ?item wdt:P244 ?lc }}
              OPTIONAL {{ ?item wdt:P227 ?gnd }} OPTIONAL {{ ?item wdt:P268 ?bnf }}
            }}"""):
            ids = d[qid(b["item"]["value"])]["ids"]
            for k in ("viaf", "ulan", "isni", "lc", "gnd", "bnf"):
                if k in b:
                    ids.setdefault(k, b[k]["value"])
    return d


# Wikidata properties that say how two people were related, for typing WKW's links later
RELATIONS = {
    "P26": "spouse", "P451": "unmarried partner", "P3373": "sibling", "P22": "father",
    "P25": "mother", "P40": "child", "P1038": "relative", "P1066": "student of",
    "P802": "student", "P184": "doctoral advisor", "P185": "doctoral student",
    "P737": "influenced by", "P1327": "partner in business or sport", "P3342": "significant person",
    "P1344": "participant in", "P8810": "parent", "P3448": "stepparent",
}


def fetch_relations(qids):
    """Statements between two of the given items, using the properties in RELATIONS."""
    qids = sorted(set(qids))
    props = " ".join(f"wdt:{p}" for p in RELATIONS)
    out = []
    for i in range(0, len(qids), 250):
        values = " ".join(f"wd:{q}" for q in qids[i:i + 250])
        for b in sparql(f"""
            SELECT ?a ?p ?b WHERE {{
              VALUES ?a {{ {values} }}
              VALUES ?p {{ {props} }}
              ?a ?p ?b. FILTER(isIRI(?b))
            }}"""):
            out.append((qid(b["a"]["value"]), qid(b["p"]["value"]), qid(b["b"]["value"])))
    wanted = set(qids)
    return [r for r in out if r[2] in wanted]


def article_links(url):
    """Wikidata items of the pages an English Wikipedia article links to, following redirects."""
    title = urllib.parse.unquote(url.rsplit("/wiki/", 1)[1]).replace("_", " ")
    api = "https://en.wikipedia.org/w/api.php"
    params = {"action": "query", "format": "json", "formatversion": 2, "titles": title,
              "generator": "links", "gplnamespace": 0, "gpllimit": "max", "redirects": 1,
              "prop": "pageprops", "ppprop": "wikibase_item"}
    qids, cont = set(), {}
    while True:
        data = cached("links", json.dumps({**params, **cont}, sort_keys=True),
                      lambda: get_json(api, {**params, **cont}))
        for p in data.get("query", {}).get("pages", []):
            q = p.get("pageprops", {}).get("wikibase_item")
            if q:
                qids.add(q)
        if "continue" not in data:
            return qids
        cont = data["continue"]


# --- Stage 3: corroboration --------------------------------------------------------------------

def corroborate(people, result, details):
    """Medium and low search matches rest on a name and a lifetime. A match is corroborated when
    Wikidata or English Wikipedia independently connects the matched item to someone WKW says
    the person knew: a Wikidata relationship, or either person's article linking to the other's.
    Records the WKW people who corroborate it in result[pid]["corroborated_by"]."""
    links = {}

    def linked(q):
        if q not in links:
            url = details[q]["enwiki"]
            links[q] = article_links(url) if url else set()
        return links[q]

    todo = [p for p in people if result[p["id"]]["qid"] and result[p["id"]].get("confidence") in ("medium", "low")]
    for n, p in enumerate(todo):
        if n % 250 == 0:
            print(f"  {n}/{len(todo)}")
        r = result[p["id"]]
        q = r["qid"]
        found = {rel["person"] for rel in r.get("relations", []) if rel["in_wkw"]}
        for k in p["knows"]:
            kq = result[k]["qid"]
            if k in found or not kq or kq == q:
                continue
            if any(rel["person"] == p["id"] for rel in result[k].get("relations", [])):
                found.add(k)
        for k in p["knows"]:
            kq = result[k]["qid"]
            if k not in found and kq and kq != q and (kq in linked(q) or q in linked(kq)):
                found.add(k)
        r["corroborated_by"] = sorted(found)


# --- Stage 2: search ---------------------------------------------------------------------------

def search(name):
    """Wikidata items whose label or alias matches name."""
    params = {"action": "wbsearchentities", "format": "json", "language": "en", "uselang": "en",
              "type": "item", "limit": 10, "search": name}
    data = cached("search", name, lambda: get_json(WD_API, params))
    return [r["id"] for r in data.get("search", [])]


def span(p):
    """(first, last) years someone was alive, from WKW's data, or None."""
    b = (p.get("birth") or {}).get("year")
    e = (p.get("death") or {}).get("year")
    if b and e:
        return (b, e)
    if b:
        return (b, b + 90)
    if e:
        return (e - 90, e)
    return None


def wd_span(x):
    b = [e["year"] for e in x["birth"]]
    e = [e["year"] for e in x["death"]]
    if b and e:
        return (min(b), max(e))
    if b:
        return (min(b), min(b) + 90)
    if e:
        return (max(e) - 90, max(e))
    return None


def year_score(ours, theirs):
    """Score for one of WKW's years against Wikidata's values for it."""
    if ours is None or not theirs:
        return 0
    diff = min(abs(ours - y["year"]) for y in theirs)
    return 3 if diff == 0 else 2 if diff <= 1 else 0 if diff <= 3 else -6


def score(p, x, title_qid, neighbour_spans):
    """How well a Wikidata item x fits person p. Returns (score, reasons)."""
    s, why = 0.0, []
    names = {fold(p["name"]), fold(p.get("alt_name"))}
    if p.get("given_name") and p.get("family_name"):
        names.add(fold(f"{p['given_name']} {p['family_name']}"))
    labels = {fold(x["label"])} | {fold(a) for a in x["aliases"]}
    if names & labels:
        s += 2
        why.append("name")
    for k in ("birth", "death"):
        ys = year_score((p.get(k) or {}).get("year"), x[k])
        if ys:
            s += ys
            why.append(f"{k} {'✓' if ys > 0 else '✗'}")
    if x["qid"] == title_qid:
        s += 2
        why.append("enwiki title")
    s += min(math.log10(1 + x["sitelinks"]), 2.5)
    # people WKW says this person knew must have been alive at the same time
    cs = wd_span(x)
    if cs and neighbour_spans:
        overlaps = sum(1 for a, b in neighbour_spans if cs[0] <= b and a <= cs[1])
        if overlaps == 0:
            s -= 10
            why.append("lifetime ✗")
        else:
            s += 2 * overlaps / len(neighbour_spans)
            why.append(f"lifetime ✓ {overlaps}/{len(neighbour_spans)}")
    return s, why


def main():
    people = json.loads((DATA / "wkw.json").read_text())
    by_id = {p["id"]: p for p in people}
    overrides = {}
    if (DATA / "wikidata-overrides.csv").exists():
        with open(DATA / "wikidata-overrides.csv", newline="", encoding="utf-8") as f:
            overrides = {r["person"]: r for r in csv.DictReader(f)}

    result = {p["id"]: {"qid": None} for p in people}

    # Stage 1
    print("Stage 1: Wikipedia links")
    wanted = defaultdict(set)
    person_titles = defaultdict(list)
    for p in people:
        for s in p["sources"]:
            t = wikipedia_title(s["url"])
            if t:
                wanted[t[0]].add(t[1])
                person_titles[p["id"]].append(t)
    resolved = {}
    for lang, titles in wanted.items():
        for t, v in wikipedia_items(lang, titles).items():
            resolved[(lang, t)] = v
    linked_qids = {v["qid"] for v in resolved.values()}
    print(f"  {sum(len(v) for v in wanted.values())} articles, {len(linked_qids)} items")
    details = fetch_details(linked_qids)

    conflicts = []
    for pid, titles in person_titles.items():
        found = []
        for lang, t in titles:
            v = resolved.get((lang, t))
            if v and not v["disambiguation"] and details[v["qid"]]["human"]:
                if v["qid"] not in [f[0] for f in found]:
                    found.append((v["qid"], f"{lang}:{t}"))
        if found:
            # prefer the item whose name matches; others are articles about relatives, works etc.
            p = by_id[pid]
            found.sort(key=lambda f: fold(details[f[0]]["label"]) != fold(p["name"]))
            result[pid] = {"qid": found[0][0], "method": "wikipedia", "confidence": "high",
                           "evidence": found[0][1]}
            if len(found) > 1:
                conflicts.append((pid, found))

    # Stage 2, in two rounds so the second can check lifetimes against more matched neighbours
    todo = [p for p in people if not result[p["id"]]["qid"]]
    print(f"Stage 2: searching for {len(todo)} people")
    cands, title_qids = {}, {}
    en = wikipedia_items("en", [p["name"] for p in todo])
    for n, p in enumerate(todo):
        if n % 250 == 0:
            print(f"  {n}/{len(todo)}")
        qs = search(p["name"])
        if p.get("alt_name"):
            qs += search(p["alt_name"].split(";")[0].strip())
        t = en.get(p["name"])
        if t and not t["disambiguation"]:
            title_qids[p["id"]] = t["qid"]
            qs.append(t["qid"])
        cands[p["id"]] = list(dict.fromkeys(qs))
    details.update(fetch_details({q for qs in cands.values() for q in qs} - set(details)))

    for rnd in (1, 2):
        def neighbour_spans(p):
            spans = []
            for k in p["knows"]:
                sp = span(by_id[k])
                if not sp and result[k]["qid"] and result[k].get("confidence") in ("high", "medium"):
                    sp = wd_span(details[result[k]["qid"]])
                if sp:
                    spans.append(sp)
            return spans

        for p in todo:
            if result[p["id"]]["qid"] and rnd == 2:
                continue
            spans = neighbour_spans(p)
            scored = []
            for q in cands[p["id"]]:
                x = details.get(q)
                if not x or not x["human"]:
                    continue
                sc, why = score(p, x, title_qids.get(p["id"]), spans)
                scored.append((sc, q, why))
            scored.sort(reverse=True)
            if not scored:
                continue
            best, nxt = scored[0], (scored[1] if len(scored) > 1 else (-99, None, []))
            has_years = bool(span(p))
            date_ok = any(w.endswith("✓") for w in best[2] if w.startswith(("birth", "death")))
            date_bad = any(w.endswith("✗") for w in best[2])
            margin = best[0] - nxt[0]
            if date_bad or "name" not in best[2]:
                conf = None
            elif has_years and date_ok and margin >= 2:
                conf = "high" if all(w.endswith("✓") for w in best[2] if w[:5] in ("birth", "death")) else "medium"
            elif not has_years and "lifetime ✗" not in best[2] and spans and (
                    margin >= 3 or (margin >= 2.5 and "enwiki title" in best[2])):
                conf = "medium" if "enwiki title" in best[2] else "low"
            elif not has_years and margin >= 3 and "enwiki title" in best[2]:
                conf = "low"
            else:
                conf = None
            entry = {"candidates": [{"qid": q, "score": round(sc, 1), "why": why} for sc, q, why in scored[:4]]}
            if conf:
                entry.update({"qid": best[1], "method": "search", "confidence": conf})
            else:
                entry["qid"] = None
            result[p["id"]] = entry

    # overrides from a person's review always win
    for pid, o in overrides.items():
        if pid in result:
            q = o["qid"].strip()
            result[pid] = {**result[pid], "qid": None if q == "none" else q, "method": "checked",
                           "confidence": "checked", "note": o.get("note")}
    missing = {r["qid"] for r in result.values() if r["qid"]} - set(details)
    if missing:
        details.update(fetch_details(missing))

    matched = {pid: r["qid"] for pid, r in result.items() if r["qid"]}
    print(f"Fetching relationships between {len(matched)} matched people")
    rels = fetch_relations(set(matched.values()))
    by_qid = defaultdict(list)
    for pid, q in matched.items():
        by_qid[q].append(pid)
    for a, prop, b in rels:
        for pa in by_qid[a]:
            for pb in by_qid[b]:
                result[pa].setdefault("relations", []).append(
                    {"property": prop, "label": RELATIONS[prop], "person": pb,
                     "in_wkw": pb in by_id[pa]["knows"]})

    print("Corroborating search matches")
    corroborate(people, result, details)

    for pid, r in result.items():
        if r["qid"]:
            r["wikidata"] = details[r["qid"]]
    (DATA / "wikidata.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    write_report(people, result, conflicts, by_qid, details)


def write_report(people, result, conflicts, by_qid, details):
    by_id = {p["id"]: p for p in people}
    conf = defaultdict(int)
    for r in result.values():
        conf[r.get("confidence") if r["qid"] else "unmatched"] += 1
    total = len(people)

    def link(q):
        return f"[{q}](https://www.wikidata.org/wiki/{q})"

    mismatches = []
    for pid, r in result.items():
        if not r["qid"]:
            continue
        p, x = by_id[pid], r["wikidata"]
        for k in ("birth", "death"):
            ours = (p.get(k) or {}).get("year")
            theirs = sorted({e["year"] for e in x[k]})
            if ours and theirs and min(abs(ours - y) for y in theirs) > (2 if (p.get(k) or {}).get("circa") else 0):
                mismatches.append(f"{p['name']} ({link(r['qid'])}, {r['confidence']}): {k} {ours} here, "
                                  f"{'/'.join(map(str, theirs))} on Wikidata")

    shared = [(q, pids) for q, pids in by_qid.items() if len(pids) > 1]
    rels = [(pid, rel) for pid, r in result.items() for rel in r.get("relations", [])]
    in_wkw = sum(1 for _, rel in rels if rel["in_wkw"])

    lines = [
        "# Wikidata reconciliation", "",
        f"- **Matched:** {total - conf['unmatched']} of {total} people",
        f"  - from their Wikipedia links: {sum(1 for r in result.values() if r.get('method') == 'wikipedia')}",
        f"  - by search, high confidence (name and all known years agree): "
        f"{sum(1 for r in result.values() if r.get('method') == 'search' and r['confidence'] == 'high')}",
        f"  - by search, medium (one year agrees, or no years but the lifetime fits the people they knew "
        f"and the English Wikipedia article has the same name): {conf['medium']}",
        f"  - by search, low (no years to check; worth reviewing): {conf['low']}",
        f"  - checked by hand: {conf['checked']}",
        f"- **Medium and low matches corroborated** by a Wikidata relationship or Wikipedia link to "
        f"someone they knew: {sum(1 for r in result.values() if r.get('corroborated_by'))} of "
        f"{conf['medium'] + conf['low']}. The rest are only `skos:closeMatch` in the RDF.",
        f"- **Unmatched:** {conf['unmatched']}",
        f"- **Relationships Wikidata records between matched people:** {len(rels)}, of which "
        f"{in_wkw} are between people WKW already links",
        "",
        "`wikidata-review.csv` lists every search match and unmatched person with its best candidates. "
        "To confirm or correct one, add it to `data/wikidata-overrides.csv` and re-run.",
        "",
        f"## Years that disagree with Wikidata ({len(mismatches)})", "",
        "Off by more than a year, or by more than two where WKW says *c.*",
        "",
    ] + [f"- {m}" for m in sorted(mismatches)] + [""]
    lines += [f"## Two WKW people matched to the same item ({len(shared)})", "",
              "Either duplicates in WKW or a wrong match."]
    lines += [""] + [f"- {link(q)} {details[q]['label']}: " + ", ".join(by_id[x]["name"] + f" (`{x}`)" for x in pids)
                     for q, pids in shared] + [""]
    lines += [f"## People with Wikipedia links to more than one person ({len(conflicts)})", "",
              "The first was used. The others are usually relatives or collaborators.", ""]
    lines += [f"- {by_id[pid]['name']}: " + ", ".join(f"{link(q)} ({e})" for q, e in found)
              for pid, found in conflicts] + [""]
    (DATA / "reports" / "wikidata.md").write_text("\n".join(lines))

    with open(DATA / "reports" / "wikidata-review.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["person", "name", "wkw_dates", "status", "confidence", "qid", "wikidata_label",
                    "wikidata_description", "wikidata_years", "other_candidates"])
        order = {"low": 0, None: 1, "medium": 2, "high": 3}
        rows = [(pid, r) for pid, r in result.items() if r.get("method") != "wikipedia"]
        rows.sort(key=lambda t: (order.get(t[1].get("confidence") if t[1]["qid"] else None, 1), t[0]))
        for pid, r in rows:
            p = by_id[pid]
            x = details.get(r["qid"]) if r["qid"] else None

            def years(x):
                b = "/".join(str(e["year"]) for e in x["birth"]) or "?"
                d = "/".join(str(e["year"]) for e in x["death"]) or "?"
                return f"{b}–{d}"
            others = [c for c in r.get("candidates", []) if c["qid"] != r["qid"]][:3]
            w.writerow([pid, p["name"], p["dates_text"] or "", p["status"],
                        r.get("confidence") if r["qid"] else "unmatched", r["qid"] or "",
                        x["label"] if x else "", x["description"] if x else "", years(x) if x else "",
                        "; ".join(f"{c['qid']} {details[c['qid']]['label']} ({years(details[c['qid']])}, "
                                  f"{details[c['qid']]['description'] or ''})" for c in others)])


if __name__ == "__main__":
    main()
