"""
Build RDF from the cleaned data.

  data/rdf/wkw.ttl        Who Knew Whom's own data: people (FOAF, schema.org), who knew whom,
                          professions (SKOS), sources, and links to Wikidata
  data/rdf/supplement.ttl birth and death dates and places that WKW doesn't give, borrowed from
                          Wikidata, in the same terms as wkw.ttl (schema:birthDate etc.)
  data/rdf/wikidata.ttl   what Wikidata says about the matched people, in Wikidata's own terms
                          (wdt:P569 etc.), so the same queries work here and on query.wikidata.org

Keeping them apart means WKW's research and Wikidata's never get mixed up: a query can use
either or all three. Load them into separate named graphs if the store supports it. Querying
wkw.ttl and supplement.ttl together gives every date and place known for a person.

Links between people are plain foaf:knows: WKW doesn't classify relationships.

Usage: uv run --with rdflib python -I tools/build_rdf.py
"""
import json
import re
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, FOAF, OWL, RDF, RDFS, SKOS, XSD

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Where the site will live. Each person is <BASE/names/{id}/#person>, described by the page
# <BASE/names/{id}/>, so the identifiers keep working if culturalcartography.net is kept.
BASE = "https://culturalcartography.net/"

SCHEMA = Namespace("https://schema.org/")
WKW = Namespace(BASE + "ns#")
WD = Namespace("http://www.wikidata.org/entity/")
WDT = Namespace("http://www.wikidata.org/prop/direct/")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")


def person(pid):
    return URIRef(f"{BASE}names/{pid}/#person")


def profession(name):
    return URIRef(f"{BASE}professions/{re.sub(r'[^a-z0-9]+', '-', name.casefold()).strip('-')}/#concept")


def year_literal(y):
    return Literal(f"{y:04d}" if y >= 0 else f"-{-y:04d}", datatype=XSD.gYear)


def trusted(w):
    """Whether a Wikidata match is sure enough to state as owl:sameAs and to borrow facts from."""
    return bool(w.get("qid")) and (w["confidence"] in ("high", "checked") or bool(w.get("corroborated_by")))


def bind(g):
    for prefix, ns in (("foaf", FOAF), ("schema", SCHEMA), ("wkw", WKW), ("wd", WD), ("wdt", WDT),
                       ("skos", SKOS), ("owl", OWL), ("dcterms", DCTERMS), ("geo", GEO)):
        g.bind(prefix, ns)


def vocabulary(g):
    """The few terms WKW needs that FOAF and schema.org don't have."""
    terms = {
        "status": "'bio' if WKW has written this person up, 'stub' if they are only linked to so far.",
        "datesText": "Birth and death as WKW gives them, e.g. '1791 (London) – 1871 (London)'.",
        "birthPlaceText": "Place of birth as WKW gives it.",
        "deathPlaceText": "Place of death as WKW gives it.",
        "approximateBirthYear": "Birth year when WKW gives it as c. (circa).",
        "approximateDeathYear": "Death year when WKW gives it as c. (circa).",
        "notToBeConfusedWith": "Another person in WKW who might be mistaken for this one.",
        "sortKey": "The key WKW sorts this person by, e.g. 'Babbage, Charles'.",
        "wordpressId": "The person's post ID in the WordPress site, for tracing records back.",
    }
    for t, comment in terms.items():
        g.add((WKW[t], RDF.type, RDF.Property))
        g.add((WKW[t], RDFS.comment, Literal(comment, lang="en")))


def build_wkw(people, wikidata):
    g = Graph()
    bind(g)
    vocabulary(g)
    for p in people:
        s = person(p["id"])
        g.add((s, RDF.type, FOAF.Person))
        g.add((s, FOAF.name, Literal(p["name"])))
        g.add((s, RDFS.label, Literal(p["name"])))
        if p["given_name"]:
            g.add((s, FOAF.givenName, Literal(p["given_name"])))
        if p["family_name"]:
            g.add((s, FOAF.familyName, Literal(p["family_name"])))
        if p["alt_name"]:
            g.add((s, SKOS.altLabel, Literal(p["alt_name"])))
        if p["sort_key"]:
            g.add((s, WKW.sortKey, Literal(p["sort_key"])))
        g.add((s, WKW.status, Literal(p["status"])))
        page = URIRef(f"{BASE}names/{p['id']}/")
        g.add((s, FOAF.isPrimaryTopicOf, page))
        g.add((page, FOAF.primaryTopic, s))
        if p["bio"]:
            g.add((s, DCTERMS.description, Literal(p["bio"], lang="en")))
        if p["dates_text"]:
            g.add((s, WKW.datesText, Literal(p["dates_text"])))
        for k, date_p, approx_p, place_p in (
                ("birth", SCHEMA.birthDate, WKW.approximateBirthYear, WKW.birthPlaceText),
                ("death", SCHEMA.deathDate, WKW.approximateDeathYear, WKW.deathPlaceText)):
            d = p[k] or {}
            if "year" in d:
                g.add((s, approx_p if d.get("circa") else date_p, year_literal(d["year"])))
            if d.get("place"):
                g.add((s, place_p, Literal(("?" if d.get("place_uncertain") else "") + d["place"])))
        for prof in p["professions"]:
            c = profession(prof)
            g.add((s, SCHEMA.hasOccupation, c))
            g.add((c, RDF.type, SKOS.Concept))
            g.add((c, SKOS.prefLabel, Literal(prof, lang="en")))
        for k in p["knows"]:
            g.add((s, FOAF.knows, person(k)))
        for k in p["disambiguation"]:
            g.add((s, WKW.notToBeConfusedWith, person(k)))
        for src in p["sources"]:
            u = URIRef(src["url"].replace(" ", "%20"))
            is_wp = re.match(r"https://[a-z\-]+\.wikipedia\.org/", src["url"])
            g.add((s, FOAF.isPrimaryTopicOf if is_wp else RDFS.seeAlso, u))
            if src["text"]:
                g.add((u, DCTERMS.title, Literal(src["text"])))
        for wp in p["wordpress_ids"]:
            g.add((s, WKW.wordpressId, Literal(wp)))
        for note in p.get("corrections", []):
            g.add((s, SKOS.editorialNote, Literal(note, lang="en")))
        w = wikidata.get(p["id"], {})
        if w.get("qid"):
            # uncorroborated search matches are only close matches until someone checks them
            g.add((s, OWL.sameAs if trusted(w) else SKOS.closeMatch, WD[w["qid"]]))
    return g


def date_literal(entries):
    """One literal for Wikidata's date, or None if it gives several or is vaguer than a year."""
    entries = [e for e in entries if e["precision"] >= 9]
    if len({e["year"] for e in entries}) != 1:
        return None
    best = max(entries, key=lambda e: e["precision"])
    if "date" in best and not best["date"].startswith("-"):
        return Literal(best["date"], datatype=XSD.date)
    return year_literal(best["year"])


def build_supplement(people, wikidata):
    """Dates and places WKW doesn't give, from trusted Wikidata matches, in wkw.ttl's terms."""
    g = Graph()
    bind(g)
    counts = {"birth date": 0, "death date": 0, "birth place": 0, "death place": 0, "people": 0,
              "impossible lifespan": 0}
    for p in people:
        w = wikidata.get(p["id"], {})
        if not trusted(w):
            continue
        x, s, added = w["wikidata"], person(p["id"]), False
        # Wikidata has the odd impossible date (James Rosenquist born in 1547): borrow neither
        # date if, with WKW's own, they would give a lifespan that can't be right
        years = {}
        for k in ("birth", "death"):
            ours = p[k] or {}
            lit = None if "year" in ours else date_literal(x[k])
            years[k] = (lit, ours["year"] if "year" in ours else int(str(lit)[:5].rstrip("-")) if lit else None)
        b, d = years["birth"][1], years["death"][1]
        if b is not None and d is not None and not 0 <= d - b <= 110:
            counts["impossible lifespan"] += 1
            years = {k: (None, None) for k in years}
        for k, date_p, place_p in (("birth", SCHEMA.birthDate, SCHEMA.birthPlace),
                                   ("death", SCHEMA.deathDate, SCHEMA.deathPlace)):
            ours = p[k] or {}
            lit = years[k][0]
            if lit is not None:
                g.add((s, date_p, lit))
                counts[f"{k} date"] += 1
                added = True
            places = x[f"{k}_place"]
            if not ours.get("place") and len(places) == 1:
                o = WD[places[0]["qid"]]
                g.add((s, place_p, o))
                if places[0]["label"]:
                    g.add((o, RDFS.label, Literal(places[0]["label"], lang="en")))
                if "lat" in places[0]:
                    g.add((o, SCHEMA.latitude, Literal(places[0]["lat"])))
                    g.add((o, SCHEMA.longitude, Literal(places[0]["lon"])))
                counts[f"{k} place"] += 1
                added = True
        counts["people"] += added
    return g, counts


def build_wikidata(wikidata):
    g = Graph()
    bind(g)
    seen_places = set()
    for w in wikidata.values():
        if not w.get("qid"):
            continue
        x = w["wikidata"]
        s = WD[x["qid"]]
        if x["label"]:
            g.add((s, RDFS.label, Literal(x["label"], lang="en")))
        if x["description"]:
            g.add((s, SCHEMA.description, Literal(x["description"], lang="en")))
        for prop, key in (("P569", "birth"), ("P570", "death")):
            for e in x[key]:
                lit = Literal(e["date"], datatype=XSD.date) if "date" in e else year_literal(e["year"])
                g.add((s, WDT[prop], lit))
        for prop, key in (("P19", "birth_place"), ("P20", "death_place"), ("P106", "occupations")):
            for e in x[key]:
                o = WD[e["qid"]]
                g.add((s, WDT[prop], o))
                if e["label"] and e["qid"] not in seen_places:
                    seen_places.add(e["qid"])
                    g.add((o, RDFS.label, Literal(e["label"], lang="en")))
                    if "lat" in e:
                        g.add((o, WDT.P625, Literal(f"Point({e['lon']} {e['lat']})", datatype=GEO.wktLiteral)))
        if x["image"]:
            g.add((s, WDT.P18, URIRef(x["image"])))
        if x["enwiki"]:
            g.add((URIRef(x["enwiki"]), SCHEMA.about, s))
        for k, prop in (("viaf", "P214"), ("ulan", "P245"), ("isni", "P213"), ("lc", "P244"),
                        ("gnd", "P227"), ("bnf", "P268")):
            if k in x["ids"]:
                g.add((s, WDT[prop], Literal(x["ids"][k])))
        for rel in w.get("relations", []):
            other = wikidata[rel["person"]]["qid"]
            g.add((s, WDT[rel["property"]], WD[other]))
    return g


def main():
    people = json.loads((DATA / "wkw.json").read_text())
    wikidata = {}
    if (DATA / "wikidata.json").exists():
        wikidata = json.loads((DATA / "wikidata.json").read_text())
    out = DATA / "rdf"
    out.mkdir(exist_ok=True)
    g = build_wkw(people, wikidata)
    g.serialize(out / "wkw.ttl", format="turtle")
    print(f"wkw.ttl: {len(g)} triples")
    if wikidata:
        g1, counts = build_supplement(people, wikidata)
        g1.serialize(out / "supplement.ttl", format="turtle")
        print(f"supplement.ttl: {len(g1)} triples; " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        g2 = build_wikidata(wikidata)
        g2.serialize(out / "wikidata.ttl", format="turtle")
        print(f"wikidata.ttl: {len(g2)} triples")


if __name__ == "__main__":
    main()
