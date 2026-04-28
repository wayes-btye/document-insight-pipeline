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

Aligned to the brief's five explicit doc types (client notes, research snippets, meeting summaries, interview transcripts, market commentary) plus a small admin / noise bucket. 101 documents total in the committed corpus.

| Type | Count | Typical length (words) | Shape |
|------|-------|-------------------------|-------|
| Client notes | 30 | 200–1500 | Sentiment-loaded prose, named characters, follow-ups, action items |
| Meeting summaries | 20 | 300–1800 | Date header, attendees, agenda, discussion bullets, action items |
| Interview transcripts | 8 | 800–2500 | Speaker labels, turn-taking, disfluencies, post-call notes |
| Research snippets | 18 | 150–900 | Compiled-by attribution, key findings, occasional quotes |
| Market commentary | 18 | 150–700 | Brief, opinionated, references to specific events |
| Edge-case noise / admin | 5 | 17–300 | Scheduling fragments, system notifications, helpdesk threads |
| **Total** | **99** | | (file count is 101 — two docs cross-counted across types) |

Length distribution is intentionally skewed: most docs short, a few very long. This stresses both the per-doc extractor (handles short noise without inventing themes) and the reduce stage (handles long docs without dropping signal). Filenames are mostly `note_NNN.txt` (~85%); the rest are topical (`apex_brief.txt`, `helmsley-renewal-brief.txt`) or dated-topical (`interview_helmsley_daniel_heath_20260919.txt`). Demonstrates the tool is glob-driven, not name-driven.

## Planted themes

Twelve themes total — ten substantive plus two distractors — distributed across documents at declared frequencies. Categorised by salience and nature. The `actual_doc_count` column reflects what ended up in the committed corpus; the eval grades against those committed counts. Full per-theme `expected_docs` lists in `eval/manifest.yaml`.

### Primary (high salience — central business signals)

| ID | Canonical name | Actual docs | Nature |
|----|----------------|-------------|--------|
| `pricing_pressure` | Pricing pressure on renewals | 27 | Explicit |
| `mid_market_churn_risk` | Rising churn signals in mid-market segment | 14 | Explicit, partly inferred |
| `integration_gap` | Native integration gap (Salesforce, HubSpot) | 25 | Explicit |
| `competitive_displacement_apex` | Losing deals to Apex Strategy Group | 26 | Explicit |

### Secondary (medium salience — meaningful but less ubiquitous)

| ID | Canonical name | Actual docs | Nature |
|----|----------------|-------------|--------|
| `partnership_relay` | Partnership opportunity with Relay Systems | 15 | Explicit |
| `onboarding_friction` | Slow time-to-value during onboarding | 10 | Mostly explicit |
| `account_concentration_risk` | Top-3-account revenue concentration (~49%) | 12 | Implicit (numbers in different docs) |

### Minor (low salience — should still surface in a thorough analysis)

| ID | Canonical name | Actual docs | Nature |
|----|----------------|-------------|--------|
| `eu_ai_act_compliance` | EU AI Act readiness for advisory deliverables | 13 | Explicit |
| `vertical_expansion_healthcare` | Healthcare vertical expansion opportunity | 9 | Explicit |
| `talent_retention_engineering` | Engineering attrition risk | 7 | Implicit, scattered |

### Distractors (should NOT be surfaced as report items)

| ID | Description | Actual docs | Tests for |
|----|-------------|-------------|-----------|
| `office_relocation` | Admin chatter about office moves, IT helpdesk | 3 | False positive theme detection on low-signal noise |
| `dismissed_consumer_pivot` | "We are NOT pivoting to consumer" — mentioned only to be dismissed | 3 | Negation handling — surfacing dismissed ideas as recommendations |
| `pure_noise` (`re_resched.txt`, `zoom_recording_notice.txt`) | Single-purpose noise files | 2 | Citation discipline — these should never appear in any report |

Theme counts ended higher than original targets in many cases. This reflects natural cross-doc theme density once the corpus was written; the manifest records the actual counts and the eval grades against those.

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

The corpus was generated interactively by Claude Opus 4.7 inside a Claude Code session, not via a regeneration script. The committed corpus is canonical; the manifest is sealed against it.

For each document the procedure was:

1. Sample a doc type, target length, and theme set per the planted-theme distribution.
2. Apply per-doc spec cards: target type and length, primary theme(s), one or two secondary theme(s), persona / author voice (one of ~15 named authors), stylistic notes (interview turn-taking, meeting-note structure, etc.), scenario context (prior conversations referenced in the doc).
3. Generate with anti-AI-slop discipline: no em dashes, banned vocabulary list (delve, leverage, robust, comprehensive, navigate, seamless, pivotal, testament, crucial, ever-evolving, multifaceted), no parallel negation, no tricolons, sentence-length variation, deliberate imperfections preserved (half-quotes, abbreviations, parenthetical asides).
4. Cross-check named entities for consistency across docs (the same person stays the same person; the same company keeps its details).
5. Record per-document theme presence in `eval/manifest.yaml` under `expected_docs`.

A reference reproducibility script (`scripts/generate_corpus.py`) is mentioned in the build plan as a future deliverable but is not part of this submission. Re-running would produce different prose with the same theme distribution; the committed corpus is what the eval grades against.

See `docs/ai-assistance.md` for the full account of what was AI-generated vs human-judged during corpus construction.

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
