"""
Suggest what kind of relationship each Who Knew Whom link records, from the bios.

WKW records only *that* two people knew each other (foaf:knows). The bios usually say how:
"friends as students", "influential teachers", "filmed making pancakes". This asks Claude to
type each link with terms from the RELATIONSHIP vocabulary (http://purl.org/vocab/relationship/),
plus a few WKW terms where it has none, quoting the sentence that supports it.

There is one request per person with a bio, covering all their links. A link between two people
who both have bios is handled once, in the request for whichever id sorts first, and that
request includes the other person's bio too.

Everything the model suggests is a suggestion: nothing here changes data/wkw.json.

  python tools/type_links.py count [--model M]      exact input tokens for every request (free)
  python tools/type_links.py pilot --model M [--n 50] [--effort E]
                                                    run a sample directly; costs money
  python tools/type_links.py submit --model M        send the whole job as a Message Batch; costs money
  python tools/type_links.py collect --model M       check the batch; once it has ended, save the results
  python tools/type_links.py evaluate FILE          score a run against Wikidata's relationships
  python tools/type_links.py repair FILE --model M  re-run requests that failed or left links out; costs money
  python tools/type_links.py sheet FILE             write a run as a CSV for the editor to review

Run with: bash -ic 'uv run --no-project --python 3.12 --with anthropic python -I tools/type_links.py ...'
(bash -ic so ~/.bashrc's ANTHROPIC_API_KEY is set.)
"""
import argparse
import json
import random
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "link-types"
PROMPT_VERSION = 3  # bump when SYSTEM, TYPES or SCHEMA change; output files are named by it

# RELATIONSHIP vocabulary terms that can apply to historical figures, and a few WKW ones for
# kinds of acquaintance it has no term for. Direction matters for the asymmetric ones.
TYPES = {
    "rel:friendOf": "friends",
    "rel:closeFriendOf": "close or lifelong friends",
    "rel:acquaintanceOf": "knew or met each other, including a single meeting; the default when the text doesn't clearly say more",
    "rel:collaboratesWith": "worked together on something: a work, an experiment, a production, a publication",
    "rel:colleagueOf": "colleagues in the same institution, movement or group",
    "rel:mentorOf": "teacher, mentor or supervisor OF the other person",
    "rel:apprenticeTo": "student, pupil or apprentice OF the other person",
    "rel:influencedBy": "influenced by the other person, through personal contact (not just reading their work)",
    "rel:employerOf": "employed the other person, or commissioned them",
    "rel:employedBy": "employed or commissioned BY the other person",
    "rel:spouseOf": "married",
    "rel:lifePartnerOf": "partners or lovers without being married",
    "rel:engagedTo": "engaged to be married",
    "rel:parentOf": "parent OF the other person",
    "rel:childOf": "child OF the other person",
    "rel:siblingOf": "brother or sister",
    "rel:livesWith": "lived together or shared a house or studio",
    "rel:neighborOf": "neighbours",
    "rel:antagonistOf": "rivals, enemies or in a public quarrel",
    "wkw:relativeOf": "related in some other way: cousin, in-law, uncle, grandparent",
    "wkw:correspondedWith": "wrote to each other",
    "wkw:classmateOf": "students together at the same school or university",
    "wkw:patronOf": "patron, supporter or champion OF the other person's work",
    "wkw:patronisedBy": "supported or championed BY the other person",
    "wkw:portrayed": "depicted the other person in a work: painted, photographed, filmed, sculpted them, or wrote a portrait of them",
    "wkw:portrayedBy": "depicted BY the other person in a work",
    "wkw:unspecified": "the texts say nothing about how they knew each other",
}

SYSTEM = f"""You are helping to catalogue Who Knew Whom, a hand-researched map of acquaintanceships between historical figures in the arts and sciences, compiled by the artist Nat Goodden. Every link between two people has been checked by the editor: they really did know each other. Your job is to say, from the short biographies provided, what kind of relationship each link was.

You will be given one person (the subject) with their biography, and a list of people the subject knew. Some of those people have a biography of their own, which may also describe the relationship.

For every listed person, return:
- person: their id, exactly as given.
- types: one or more relationship types from the list below. Use every type the texts support (for example both rel:mentorOf and rel:friendOf). Types are always read from the subject's side: "rel:mentorOf" means the subject taught the other person; "rel:apprenticeTo" means the subject was taught by them.
- evidence: the words from a biography that support the types, copied exactly, character for character (a phrase or sentence, not more). Leave it empty if nothing in the texts mentions the relationship.
- evidence_from: "subject" or "other" for whose biography the evidence comes from, or "none".
- confidence: "high" if the text states the relationship plainly, "medium" if it is implied (for example a name in a list of "friends and correspondents"), "low" if you are inferring from context.
- discrepancy_type and discrepancy: anything in the texts that doesn't fit the editor's record that these two people knew each other, or that the editor should check. Choose one type:
  - never_met: a biography says they never met, or knew each other only by reputation, through letters or through someone else.
  - contradiction: the two biographies contradict each other, or a biography contradicts itself.
  - ambiguous_name: the text names someone (often by surname only) who may be a different person from the one listed.
  - dates: their dates, or the dates in the text, make the relationship unlikely, or a date given looks wrong.
  - not_mentioned: neither text mentions the other person at all, so nothing here supports the link.
  - other: anything else the editor should check.
  - none: nothing to flag.
  In discrepancy, say what the problem is in one sentence, or leave it empty for none. Don't flag something that isn't a problem.

Rules:
- Use only what the biographies say. Do not add relationships you know of from elsewhere, even if you are sure of them: the point is to record what this source says. If the texts say nothing about how two people knew each other, use wkw:unspecified with empty evidence.
- Biographies often refer to people by surname only ("Herschel", "Ginsberg"). Match them to the listed people by name and dates.
- When in doubt between rel:friendOf, rel:colleagueOf and rel:acquaintanceOf, choose rel:acquaintanceOf. Use rel:friendOf only when a text calls them friends or describes a friendship, and rel:colleagueOf only when they worked in the same institution, group or movement. A list like "among his friends were A, B and C" supports rel:friendOf for each of them; "he mixed with a group including A, B and C" or "he knew A, B and C" supports only rel:acquaintanceOf.
- Taking lessons from someone makes them a teacher (rel:apprenticeTo), even if the lessons were paid for. An interview or a review is not a portrait.
- Return exactly one entry for every listed person, in the order given.

Relationship types:
""" + "\n".join(f"- {k}: {v}" for k, v in TYPES.items())

SCHEMA = {
    "type": "object",
    "properties": {
        "links": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "person": {"type": "string"},
                    "types": {"type": "array", "items": {"type": "string", "enum": list(TYPES)}},
                    "evidence": {"type": "string"},
                    "evidence_from": {"type": "string", "enum": ["subject", "other", "none"]},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "discrepancy_type": {"type": "string", "enum": [
                        "none", "never_met", "contradiction", "ambiguous_name", "dates", "not_mentioned", "other"]},
                    "discrepancy": {"type": "string"},
                },
                "required": ["person", "types", "evidence", "evidence_from", "confidence",
                             "discrepancy_type", "discrepancy"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["links"],
    "additionalProperties": False,
}


def load():
    people = {p["id"]: p for p in json.loads((DATA / "wkw.json").read_text())}
    return people


def card(p):
    bits = [p["name"]]
    if p["dates_text"]:
        bits.append(p["dates_text"])
    if p["professions"]:
        bits.append(", ".join(p["professions"]))
    return " — ".join(bits)


def links_for(people, pid):
    """The links the request for pid covers: each two-bio link goes to the id that sorts first."""
    return [k for k in people[pid]["knows"] if not (people[k]["bio"] and k < pid)]


def build(people, pid, only=None):
    """The user message for one subject, optionally for only some of their links."""
    p = people[pid]
    lines = [f"SUBJECT: {card(p)} (id: {pid})", "", "Biography:", p["bio"], "", "PEOPLE THE SUBJECT KNEW:"]
    for n, k in enumerate(only or links_for(people, pid), 1):
        o = people[k]
        lines += ["", f"{n}. {card(o)} (id: {k})"]
        if o["bio"]:
            lines += ["Biography:", o["bio"]]
    return "\n".join(lines)


def params(people, pid, model, effort, only=None, max_tokens=None):
    links = only or links_for(people, pid)
    return {
        "model": model,
        # thinking counts toward max_tokens; about 120 tokens of output per link
        "max_tokens": max_tokens or min(64000, 4000 + 200 * len(links)),
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": build(people, pid, only)}],
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
    }


def subjects(people):
    return sorted(pid for pid, p in people.items() if p["bio"] and links_for(people, pid))


def cmd_count(args):
    people = load()
    client = anthropic.Anthropic()
    ids = subjects(people)

    def count(pid):
        p = params(people, pid, args.model, "medium")
        for attempt in range(6):
            try:
                return pid, client.messages.count_tokens(
                    model=p["model"], system=p["system"], messages=p["messages"]).input_tokens
            except anthropic.RateLimitError:
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"count failed for {pid}")

    with ThreadPoolExecutor(4) as pool:
        counts = dict(pool.map(count, ids))
    system_only = client.messages.count_tokens(
        model=args.model, system=SYSTEM, messages=[{"role": "user", "content": "x"}]).input_tokens
    total = sum(counts.values())
    n_links = sum(len(links_for(people, pid)) for pid in ids)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"token-counts-{args.model}.json").write_text(json.dumps(counts, indent=1))
    print(json.dumps({"model": args.model, "requests": len(ids), "links": n_links,
                      "input_tokens": total, "system_prompt_tokens": system_only,
                      "largest_request": max(counts.values())}, indent=1))


def run_one(client, people, pid, model, effort, only=None, max_tokens=None):
    p = params(people, pid, model, effort, only, max_tokens)
    # fallbacks: if a safety classifier declines, the API re-runs the request on another model
    # (Haiku has no server-side fallback, so its refusals are just recorded)
    extra = {} if "haiku" in model else {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    with client.beta.messages.stream(**p, **extra) as stream:
        msg = stream.get_final_message()
    out = {"subject": pid, "model": msg.model, "stop_reason": msg.stop_reason,
           "usage": msg.usage.model_dump(), "links": None}
    if msg.stop_reason == "end_turn":
        text = next(b.text for b in msg.content if b.type == "text")
        out["links"] = json.loads(text)["links"]
    return out


def cmd_pilot(args):
    people = load()
    client = anthropic.Anthropic()
    ids = subjects(people)
    random.Random(args.seed).shuffle(ids)
    ids = ids[:args.n]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"pilot-v{PROMPT_VERSION}-{args.model}-{args.effort}.jsonl"
    done = set()
    if path.exists():
        done = {json.loads(line)["subject"] for line in path.open()}
    todo = [pid for pid in ids if pid not in done]
    print(f"{len(todo)} requests to {args.model} at effort {args.effort} -> {path}")

    def work(pid):
        for attempt in range(4):
            try:
                return run_one(client, people, pid, args.model, args.effort)
            except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError) as e:
                print(f"  {pid}: {type(e).__name__}, retrying")
                time.sleep(10 * (attempt + 1))
        return {"subject": pid, "error": "failed after retries"}

    with ThreadPoolExecutor(4) as pool, path.open("a") as f:
        for n, r in enumerate(pool.map(work, todo), 1):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(f"  {n}/{len(todo)} {r['subject']}: {r.get('stop_reason') or r.get('error')}")
    report_usage(path, args.model)


def batch_path(model, effort):
    return OUT / f"batch-v{PROMPT_VERSION}-{model}-{effort}.json"


def cmd_submit(args):
    """Sends every request as one Message Batch (half price; usually done within an hour)."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    people = load()
    client = anthropic.Anthropic()
    path = batch_path(args.model, args.effort)
    if path.exists():
        sys.exit(f"{path} exists: this batch was already submitted. Run collect, or delete it to resubmit.")
    ids = subjects(people)
    # custom_id allows only [a-zA-Z0-9_-]{1,64}, so requests are numbered and the ids kept here
    # (server-side fallbacks aren't available on the Batches API; refusals are recorded instead)
    requests = [Request(custom_id=f"s{n}", params=MessageCreateParamsNonStreaming(
        **params(people, pid, args.model, args.effort))) for n, pid in enumerate(ids)]
    batch = client.messages.batches.create(requests=requests)
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"batch_id": batch.id, "model": args.model, "effort": args.effort,
                                "prompt_version": PROMPT_VERSION, "subjects": ids}, indent=1))
    print(f"Submitted batch {batch.id}: {len(ids)} requests. Saved to {path}")


def cmd_collect(args):
    """Checks the batch and, once it has ended, writes the results like a pilot run."""
    people = load()
    client = anthropic.Anthropic()
    info = json.loads(batch_path(args.model, args.effort).read_text())
    batch = client.messages.batches.retrieve(info["batch_id"])
    print(f"Batch {batch.id}: {batch.processing_status}, {batch.request_counts.model_dump()}")
    if batch.processing_status != "ended":
        return
    out = OUT / f"run-v{PROMPT_VERSION}-{args.model}-{args.effort}.jsonl"
    with out.open("w") as f:
        for result in client.messages.batches.results(batch.id):
            pid = info["subjects"][int(result.custom_id[1:])]
            r = {"subject": pid, "links": None}
            if result.result.type == "succeeded":
                msg = result.result.message
                r.update({"model": msg.model, "stop_reason": msg.stop_reason, "usage": msg.usage.model_dump()})
                if msg.stop_reason == "end_turn":
                    text = next(b.text for b in msg.content if b.type == "text")
                    r["links"] = json.loads(text)["links"]
            else:
                r["error"] = result.result.type
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {out}")
    report_usage(out, args.model, batch=True)


def cmd_repair(args):
    """Re-runs, directly, the requests in a run that failed or left links out, and merges them in."""
    people = load()
    client = anthropic.Anthropic()
    path = Path(args.file)
    rows = [json.loads(line) for line in path.open(encoding="utf-8")]
    todo = []
    for r in rows:
        expected = links_for(people, r["subject"])
        got = {x["person"] for x in r["links"] or []}
        # drop answers about people who aren't in the list (e.g. a misspelt id)
        if r["links"]:
            r["links"] = [x for x in r["links"] if x["person"] in expected]
        missing = [k for k in expected if k not in got]
        if missing:
            todo.append((r, missing))
    print(f"Repairing {sum(len(m) for _, m in todo)} links in {len(todo)} requests")
    repairs = []
    for r, missing in todo:
        new = run_one(client, people, r["subject"], args.model, args.effort, only=missing, max_tokens=16000)
        print(f"  {r['subject']}: {len(missing)} links, {new['stop_reason']}")
        if new["links"]:
            r["links"] = (r["links"] or []) + [x for x in new["links"] if x["person"] in missing]
            r.setdefault("repaired_by", []).append(new["model"])
        repairs.append(new)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    log = path.with_name(path.stem + "-repairs.jsonl")
    with log.open("a", encoding="utf-8") as f:
        for new in repairs:
            f.write(json.dumps(new, ensure_ascii=False) + "\n")
    report_usage(log, args.model)


# Prices per million tokens (claude-api skill, cached 2026-10-06): input, output, cache read
PRICES = {"claude-opus-5-5": (4.0, 20.0, 0.20), "claude-sonnet-5-5": (2.0, 10.0, 0.20),
          "claude-haiku-5-5": (0.10, 0.50, 0.01)}


def report_usage(path, model, batch=False):
    rows = [json.loads(line) for line in path.open()]
    u = Counter()
    for r in rows:
        for k, v in (r.get("usage") or {}).items():
            if isinstance(v, int):
                u[k] += v
    pi, po, pc = PRICES.get(model, (0, 0, 0))
    cost = (u["input_tokens"] * pi + u["cache_creation_input_tokens"] * pi * 1.25
            + u["cache_read_input_tokens"] * pc + u["output_tokens"] * po) / 1e6
    if batch:
        cost /= 2  # the Batches API is half price
    print(json.dumps({"requests": len(rows), **u, "cost_usd": round(cost, 3)}, indent=1))


# Wikidata properties (from tools/wikidata.py) and the types that agree with them, read from the
# subject's side when Wikidata says "subject P other"
WIKIDATA_TYPES = {
    "P26": {"rel:spouseOf"}, "P451": {"rel:lifePartnerOf", "rel:spouseOf"},
    "P3373": {"rel:siblingOf"}, "P22": {"rel:childOf"}, "P25": {"rel:childOf"},
    "P8810": {"rel:childOf"}, "P40": {"rel:parentOf"}, "P1038": {"wkw:relativeOf", "rel:siblingOf",
                                                                  "rel:parentOf", "rel:childOf"},
    "P1066": {"rel:apprenticeTo"}, "P802": {"rel:mentorOf"}, "P184": {"rel:apprenticeTo"},
    "P185": {"rel:mentorOf"}, "P737": {"rel:influencedBy", "rel:apprenticeTo"},
    "P1327": {"rel:collaboratesWith"},
}
INVERSE = {"rel:mentorOf": "rel:apprenticeTo", "rel:apprenticeTo": "rel:mentorOf",
           "rel:parentOf": "rel:childOf", "rel:childOf": "rel:parentOf",
           "rel:employerOf": "rel:employedBy", "rel:employedBy": "rel:employerOf",
           "wkw:patronOf": "wkw:patronisedBy", "wkw:patronisedBy": "wkw:patronOf",
           "wkw:portrayed": "wkw:portrayedBy", "wkw:portrayedBy": "wkw:portrayed"}


def cmd_evaluate(args):
    people = load()
    wikidata = json.loads((DATA / "wikidata.json").read_text())
    rows = [json.loads(line) for line in open(args.file)]
    problems = Counter()
    suggested = {}
    for r in rows:
        if not r.get("links"):
            problems[f"no result ({r.get('stop_reason') or r.get('error')})"] += 1
            continue
        expected = links_for(people, r["subject"])
        got = {x["person"]: x for x in r["links"]}
        problems["links missing from answer"] += len(set(expected) - set(got))
        problems["unknown ids in answer"] += len(set(got) - set(expected))
        for k in expected:
            if k not in got:
                continue
            x = got[k]
            ev = x["evidence"]
            src = people[r["subject"]]["bio"] if x["evidence_from"] == "subject" else (people[k]["bio"] or "")
            if ev and ev not in src:
                problems["evidence not an exact quote"] += 1
            suggested[(r["subject"], k)] = set(x["types"])
            suggested[(k, r["subject"])] = {INVERSE.get(t, t) for t in x["types"]}

    # Wikidata as a check: for each relationship it records between two linked people we ran
    hits = misses = 0
    by_prop = defaultdict(lambda: [0, 0])
    examples = []
    for pid, w in wikidata.items():
        for rel in w.get("relations", []):
            key = (pid, rel["person"])
            if key not in suggested or rel["property"] not in WIKIDATA_TYPES:
                continue
            ok = bool(suggested[key] & WIKIDATA_TYPES[rel["property"]])
            hits += ok
            misses += not ok
            by_prop[rel["label"]][0 if ok else 1] += 1
            if not ok and len(examples) < 15:
                examples.append(f"{people[pid]['name']} {rel['label']} {people[rel['person']]['name']}: "
                                f"suggested {sorted(suggested[key])}")
    types = Counter(t for k, v in suggested.items() if k[0] < k[1] for t in v)
    print(json.dumps({"links_typed": len(suggested) // 2, "problems": problems,
                      "wikidata_agreement": f"{hits}/{hits + misses}",
                      "by_wikidata_property": {k: f"{v[0]}/{sum(v)}" for k, v in by_prop.items()},
                      "type_counts": types.most_common()}, indent=1, ensure_ascii=False))
    print("\nDisagreements with Wikidata:")
    for e in examples:
        print(" ", e)
    flagged = [(r["subject"], x) for r in rows for x in r.get("links") or []
               if x.get("discrepancy_type", "none" if not x.get("discrepancy") else "other") != "none"]
    print(f"\nDiscrepancies flagged ({len(flagged)}): "
          + json.dumps(Counter(x.get("discrepancy_type", "?") for _, x in flagged)))
    for pid, x in flagged[:args.show]:
        print(f"  [{x.get('discrepancy_type', '?')}] {people[pid]['name']} – {people[x['person']]['name']}: "
              f"{x['discrepancy']}")


def cmd_sheet(args):
    """Writes the suggestions as a spreadsheet for the editor to review."""
    import csv
    people = load()
    wikidata = json.loads((DATA / "wikidata.json").read_text())
    rows = [json.loads(line) for line in open(args.file, encoding="utf-8")]
    order = {"never_met": 0, "contradiction": 1, "ambiguous_name": 2, "dates": 3, "other": 4,
             "not_mentioned": 5, "none": 6}
    conf = {"low": 0, "medium": 1, "high": 2}

    def born(pid):
        y = (people[pid]["birth"] or {}).get("year")
        w = wikidata.get(pid, {})
        if not y and w.get("qid") and w["wikidata"]["birth"]:
            y = min(e["year"] for e in w["wikidata"]["birth"])
        return y

    def check(a, b, types):
        """A teacher or parent born well after their pupil or child: reversed, or the wrong person."""
        ya, yb = born(a), born(b)
        older = {"rel:mentorOf": "teacher", "rel:parentOf": "parent"}
        younger = {"rel:apprenticeTo": "teacher", "rel:childOf": "parent"}
        for t, role in older.items():
            if t in types and ya and yb and ya > yb + 5:
                return f"{people[a]['name']} (b. {ya}) is given as {people[b]['name']}'s {role} but was born {ya - yb} years later: reversed, or the wrong person"
        for t, role in younger.items():
            if t in types and ya and yb and yb > ya + 5:
                return f"{people[b]['name']} (b. {yb}) is given as {people[a]['name']}'s {role} but was born {yb - ya} years later: reversed, or the wrong person"
        return ""

    out = []
    for r in rows:
        for x in r.get("links") or []:
            a, b = r["subject"], x["person"]
            if b not in people:
                continue
            wd = [rel["label"] for rel in wikidata.get(a, {}).get("relations", []) if rel["person"] == b]
            wd += [f"(reverse) {rel['label']}" for rel in wikidata.get(b, {}).get("relations", [])
                   if rel["person"] == a]
            out.append({
                "person": people[a]["name"], "knew": people[b]["name"],
                "suggested_types": "; ".join(t.split(":")[1] for t in x["types"]),
                "evidence": x["evidence"], "evidence_from": {"subject": people[a]["name"], "other": people[b]["name"]}
                .get(x["evidence_from"], ""),
                "confidence": x["confidence"],
                "discrepancy_type": x.get("discrepancy_type", ""), "discrepancy": x.get("discrepancy", ""),
                "wikidata_says": "; ".join(wd),
                "automatic_check": check(a, b, set(x["types"])),
                "decision": "", "notes": "",
                "person_id": a, "knew_id": b,
            })
    out.sort(key=lambda o: (not o["automatic_check"], order.get(o["discrepancy_type"], 9), conf.get(o["confidence"], 3),
                            o["person"].casefold(), o["knew"].casefold()))
    path = OUT / f"review-{Path(args.file).stem}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # -sig so Excel reads the accents
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"Wrote {len(out)} rows to {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("count")
    c.add_argument("--model", default="claude-opus-5-5")
    p = sub.add_parser("pilot")
    p.add_argument("--model", required=True)
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--effort", default="medium")
    p.add_argument("--seed", type=int, default=1)
    e = sub.add_parser("evaluate")
    e.add_argument("file")
    e.add_argument("--show", type=int, default=60, help="how many discrepancies to print")
    rp = sub.add_parser("repair")
    rp.add_argument("file")
    rp.add_argument("--model", required=True)
    rp.add_argument("--effort", default="medium")
    h = sub.add_parser("sheet")
    h.add_argument("file")
    b = sub.add_parser("submit")
    b.add_argument("--model", required=True)
    b.add_argument("--effort", default="medium")
    g = sub.add_parser("collect")
    g.add_argument("--model", required=True)
    g.add_argument("--effort", default="medium")
    args = ap.parse_args()
    {"count": cmd_count, "pilot": cmd_pilot, "evaluate": cmd_evaluate,
     "submit": cmd_submit, "collect": cmd_collect, "sheet": cmd_sheet, "repair": cmd_repair}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
