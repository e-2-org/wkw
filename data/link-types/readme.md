# Relationship types: the review sheet

## How the data was reconciled

First I exported everything from the WordPress database and tidied it up. 26 people had ended up in there twice (usually once from the old wiki import and once added by hand, sometimes without the accents), so I merged them, keeping the accented spelling. The birth/death text was split into years and places. That leaves 3,453 people and 12,400 "knew" links.

Then I matched the people to [Wikidata](https://www.wikidata.org/), the database behind Wikipedia. About a third came straight from the Wikipedia links you'd added. The rest were found by searching on names and checking that the dates fitted, including that each person was alive at the same time as the people they're linked to. 3,250 of the 3,453 are matched. That brings in dates, places, occupations, portraits and library catalogue IDs, and it turned up a few things for later: about 35 people who are probably in twice under different spellings (Bertholt/Bertolt Brecht, three versions of Jung), and 20 dates that disagree with Wikidata, mostly typos (Wordsworth dying in 1950, for example). I haven't changed any of those yet.

The links themselves only say that two people knew each other. To suggest what kind of relationship each one was, an AI model (Claude) read your biographies of both people and picked from a standard list of relationship types, quoting the words it based each choice on. It was told to use only what your biographies say, not anything it knows from elsewhere, and to flag anything that doesn't fit. Where Wikidata records a relationship between the same two people, it's shown alongside; the two agree about 80% of the time.

The list is the [RELATIONSHIP vocabulary](http://purl.org/vocab/relationship/), an extension of FOAF for the different ways people know each other: each of its types, like `friendOf` or `mentorOf`, is defined as a more specific kind of FOAF's `knows`. So a typed link still counts as "knows", and the data can be searched either way: everyone someone knew, or only the people they taught. The few types I've added for things it doesn't cover (`correspondedWith`, `classmateOf`, `patronOf` / `patronisedBy`, `portrayed` / `portrayedBy`, `relativeOf` and `unspecified`) will be defined the same way.

## The CSV

[`review-run-v3-claude-sonnet-5-5-medium.csv`](review-run-v3-claude-sonnet-5-5-medium.csv) has one row for each of the 12,400 links, and opens in Excel or LibreOffice (accents included). Read each row as "*person* is *type* of *knew*": `friendOf; correspondedWith` means they were friends and wrote to each other, `mentorOf` means *person* taught *knew*, and `apprenticeTo` is the other way round.

| Column | What it holds |
|---|---|
| `person`, `knew` | The two people |
| `suggested_types` | The suggested types, separated by semicolons |
| `evidence`, `evidence_from` | The words they're based on, and whose biography those are from |
| `confidence` | `high` (stated plainly), `medium` (implied), `low` (inferred) |
| `discrepancy_type`, `discrepancy` | Anything that doesn't fit: `never_met`, `contradiction`, `ambiguous_name` (a surname that could be someone else), `dates`, `not_mentioned` or `other` |
| `wikidata_says` | Wikidata's version, where it has one |
| `automatic_check` | A check on teachers and parents being older than their pupils and children |
| `decision`, `notes` | For you |
| `person_id`, `knew_id` | Please leave these alone, as they're how I match your answers back to the data |

## How to fill it in

In `decision`, put:

- `ok`: the suggestions are right
- the right types, separated by semicolons (e.g. `friendOf; patronOf`): if they're wrong or something's missing
- `reverse`: the right relationship, but the wrong way round
- `wrong person`: the link goes to the wrong person (say who in `notes`)
- `remove`: they didn't actually know each other

Leave it blank if you haven't looked at a row, and use `notes` for anything else (a wrong date, a duplicate, a source).

You don't need to go through all 12,400 rows. The sheet is sorted so that the ones that most need you come first:

1. **Rows 2–113:** a "teacher" or "parent" born after their pupil or child. Most are just reversed, but a few are the wrong person (Bewick's pupil William Harvey is linked to William Harvey the physician).
2. **Rows 114–1620:** something flagged: never met, contradictions, ambiguous names, dates and so on.
3. **Rows 1621–4505:** neither biography mentions the other person, so most are `unspecified`. Only worth filling in where you know how they knew each other.
4. **Rows 4506 onwards:** nothing flagged, least certain first. A skim is plenty.

### The types you can use

| | |
|---|---|
| Knowing each other | `acquaintanceOf`, `friendOf`, `closeFriendOf`, `antagonistOf` (rivals or enemies) |
| Work | `collaboratesWith`, `colleagueOf`, `correspondedWith`, `classmateOf`, `employerOf` / `employedBy` (including commissions), `patronOf` / `patronisedBy` |
| Teaching | `mentorOf` / `apprenticeTo`, `influencedBy` (through personal contact, not just their work) |
| Family and home | `spouseOf`, `lifePartnerOf`, `engagedTo`, `parentOf` / `childOf`, `siblingOf`, `relativeOf`, `livesWith`, `neighborOf` |
| Art | `portrayed` / `portrayedBy` (painted, photographed, sculpted, filmed or wrote a portrait of) |
| None of these | `unspecified`: nothing says how they knew each other |

If none of them fits, describe the relationship in `notes` and I'll find or add a term.

## What it's for

Nothing in your data changes until you've been through it. Your decisions turn the plain "knew" links into typed ones, so the new site will be able to answer questions like who taught whom or who painted whom, and the graph can show different kinds of connection differently. When you're done, save it as a CSV (or a spreadsheet is fine) and send it back.
