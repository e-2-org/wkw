"""
Build RDF from the cleaned data.

  data/rdf/wkw.ttl        Who Knew Whom's own data: people (FOAF, schema.org), who knew whom,
                          professions (SKOS), sources, and links to Wikidata
  data/rdf/wikidata.ttl   what Wikidata says about the matched people, in Wikidata's own terms
                          (wdt:P569 etc.), so the same queries work here and on query.wikidata.org

Keeping them apart means WKW's research and Wikidata's never get mixed up: a query can use
either or both. Load them into separate named graphs if the store supports it.

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
        w = wikidata.get(p["id"], {})
        if w.get("qid"):
            # low-confidence matches are only close matches until someone checks them
            rel = SKOS.closeMatch if w["confidence"] == "low" else OWL.sameAs
            g.add((s, rel, WD[w["qid"]]))
    return g


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
        g2 = build_wikidata(wikidata)
        g2.serialize(out / "wikidata.ttl", format="turtle")
        print(f"wikidata.ttl: {len(g2)} triples")


if __name__ == "__main__":
    main()
