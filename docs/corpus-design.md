# Corpus Design

## Why synthetic

The repository ships with a synthetic corpus of ~100 fictional business documents in `input_docs/`. Synthetic over real for three reasons:

1. **Controlled ground truth.** We declare the planted themes, frequencies, and intended distractors upfront in `eval/manifest.yaml`. The evaluation harness grades against this fixed manifest. With real documents we'd have no objective recall measure.
2. **Defensible test set semantics.** The corpus is built once and locked. The extraction pipeline never reads the manifest. Build-time and grade-time are procedurally separated — the tool is structurally blind to its own grading rubric.
3. **No data hygiene burden.** No PII, no confidentiality, no licensing. Anyone can clone and run the eval.

We acknowledge the tradeoff explicitly. Synthetic eval corpora are documented to **underestimate task difficulty** because surface overlap between corpus and manifest can make matching trivial. The corpus design below pushes back against this.

## Scenario

Documents represent a quarter's worth of operational artifacts collected by the commercial team at a fictional B2B advisory firm — **Meridian Advisory** — that helps mid-market SaaS and services companies on commercial strategy (pricing, GTM, retention).

The pile reflects realistic operational chaos:
- Authored by different people with different writing styles
- Different formats (some structured, some prose, some bulleted)
- Different signal-to-noise ratios (some are dense with information; some are mostly admin)
- Some documents reference one another or contain similar information from different angles
- Most are from the past quarter; a few are older

The fictional names (Meridian, the competitor "Apex", the partner "Relay Systems") are deliberately bland and unmemorable. They exist to give the corpus internal consistency, not to be remembered.

## Document type taxonomy

Six types, each with a different shape and tone. Counts approximate ~100 total.

| Type | Count | Typical length (words) | Shape |
|------|-------|-------------------------|-------|
| Client meeting notes | 25 | 300–1500 | Date header, attendees, agenda, discussion bullets, action items |
| Client / prospect call summaries | 20 | 200–800 | Short prose, sentiment-loaded, follow-ups |
| Internal memos | 15 | 600–2500 | Subject line, TL;DR, body, sometimes recommendations |
| Market commentary / analyst clippings | 15 | 150–600 | Brief, opinionated, references to specific events |
| Research snippets | 10 | 200–1000 | Source attribution, key findings, occasional quotes |
| Admin / scheduling / low-signal | 15 | 80–300 | Office logistics, scheduling threads, system notifications |

Length distribution is intentionally skewed: most docs short, a few very long. This stresses both the per-doc extractor (handles short noise without inventing themes) and the reduce stage (handles long docs without dropping signal).

## Planted themes

Twelve themes total, distributed across documents at declared frequencies. Categorised by salience and nature.

### Primary (high salience — central business signals)

| ID | Canonical name | Target docs | Nature |
|----|----------------|-------------|--------|
| `pricing_pressure` | Pricing pressure on renewals | 18 | Explicit |
| `mid_market_churn_risk` | Rising churn signals in mid-market segment | 14 | Explicit, partly inferred |
| `integration_gap` | Native integration gap (Salesforce, HubSpot) | 16 | Explicit |
| `competitive_displacement_apex` | Losing deals to competitor "Apex" | 12 | Explicit |

### Secondary (medium salience — meaningful but less ubiquitous)

| ID | Canonical name | Target docs | Nature |
|----|----------------|-------------|--------|
| `partnership_relay` | Partnership opportunity with Relay Systems | 9 | Explicit |
| `onboarding_friction` | Slow time-to-value during onboarding | 10 | Mostly explicit |
| `account_concentration_risk` | Top 3 clients ≈ 38% of revenue | 7 | Implicit (numbers in different docs) |

### Minor (low salience — should still surface in a thorough analysis)

| ID | Canonical name | Target docs | Nature |
|----|----------------|-------------|--------|
| `eu_ai_act_compliance` | EU AI Act readiness for client deliverables | 5 | Explicit |
| `vertical_expansion_healthcare` | Inbound healthcare interest as expansion lane | 4 | Explicit |
| `talent_retention_engineering` | Engineering attrition signals | 5 | Implicit, scattered |

### Distractors (should NOT be surfaced as report items)

| ID | Description | Target docs | Tests for |
|----|-------------|-------------|-----------|
| `office_relocation` | Admin chatter about office moves | 4 | False positive theme detection on low-signal noise |
| `dismissed_consumer_pivot` | "We are NOT pivoting to consumer" — mentioned only to be dismissed | 3 | Negation handling — surfacing dismissed ideas as recommendations |

## Deliberate difficulty mechanics

To counter synthetic-eval-too-easy, the corpus uses these mechanics:

1. **Theme overlap.** Docs commonly carry 2–4 themes simultaneously. A naive bag-of-words clusterer that splits on dominant keyword will conflate `pricing_pressure` with `competitive_displacement_apex` (clients often cite Apex's pricing in renewal pushback). The tool needs to surface them as distinct themes that frequently co-occur.
2. **Implicit themes.** `account_concentration_risk` is never stated outright. It surfaces only if the tool aggregates revenue figures and client mentions across multiple memos. This tests the reduce stage's ability to derive insight from cross-document patterns.
3. **Negation / dismissal.** `dismissed_consumer_pivot` appears in three documents in the form "the partner asked about consumer; we declined" or "we considered consumer; not pursuing." A naive theme extractor will flag it as an opportunity. A good one will recognise dismissal.
4. **Variable salience.** Some themes are mentioned briefly across many docs (`integration_gap` — short complaints scattered everywhere). Others appear in fewer docs but with more weight (`partnership_relay` — three substantive memos). Salience must come from semantic weight, not raw count.
5. **Distractor noise docs.** Admin/scheduling docs are ~15% of the corpus and contain no strategic signal. A poorly-tuned extractor will hallucinate themes from them.
6. **Near-duplicate angles.** A few topics are covered from 2–3 perspectives across different doc types (e.g. a pricing-pressure call summary, the resulting internal memo, and an analyst clipping mentioning the same client). Tests deduplication.
7. **Stylistic variety.** Writing styles vary — terse bullets, dense prose, half-finished sentences, abbreviations, occasional typos. Real docs aren't clean.

## Generation procedure

Documents are generated by a separate script (`scripts/generate_corpus.py`) that:

1. Reads the theme manifest from `eval/manifest.yaml`.
2. For each target document, samples a doc type, target length, and theme set per the planted-theme distribution.
3. Calls the LLM with a structured prompt: doc type, length budget, themes to weave in (with intended salience), stylistic notes, scenario context. Prompts emphasise authenticity over polish — natural variation in tone, occasional informality, realistic noise.
4. Saves outputs as `input_docs/note_001.txt` through `note_100.txt`.
5. Records, per document, which themes were planted (used afterwards to populate `expected_docs` per theme in the manifest).

Generation runs once and the outputs are committed. The manifest is then locked.

The generation script is committed for transparency. Anyone can reproduce the corpus from a fresh run, though the actual committed corpus is the canonical one — re-running would produce slightly different prose with the same theme distribution.

## Quality gates before locking

Before locking the corpus and manifest:

1. **Length distribution check.** Histogram should match target — most short, long tail.
2. **Theme density check.** Each planted theme appears in roughly its target document count (±20%).
3. **Spot-read 10 random docs.** Verify variety, plausibility, no LLM-slop tells (no "I hope this helps", no "in conclusion"), no broken structure.
4. **Distractor placement.** Office-relocation and consumer-pivot mentions read naturally, not as transparent test cases.
5. **No leakage from manifest into generated text.** Theme IDs (`pricing_pressure`) never appear verbatim in any document. Canonical theme names appear naturally where they would, not as headers.

If any gate fails, regenerate the failing slice.

## Why not real public data

We considered chunking real public business documents (open earnings calls, BIS reports, public consultancy decks). Rejected because:
- We can't plant controlled themes — eval becomes qualitative
- Citation precision becomes ambiguous (themes are ours; doc content is theirs)
- Attribution / licensing concerns even for public material
- Domain bleed (real consultancy docs would tell the LLM "this is consulting" too cleanly)

A hybrid approach — real-document structure with synthetic content — adds complexity without clearly improving signal for this task. We chose the simpler, more controllable option and document the trade-off.

## Limitations of this corpus

- It's a single-quarter snapshot of one fictional firm. A tool that performs well on Meridian's docs may not generalise to legal contracts or scientific literature.
- Themes are pre-selected; the corpus cannot test the tool's ability to discover an entirely unanticipated theme that we didn't think to plant.
- Document length distribution is moderate. The tool's behaviour on much longer (50K+ word) documents is not exercised here.
- All documents are in English.
