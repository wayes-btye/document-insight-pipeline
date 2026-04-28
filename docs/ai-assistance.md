# AI Assistance Note

This document records how AI was used in building this project. It exists for two reasons:
1. The build process is itself a deliberate use of AI tooling, and being transparent about it is part of the project's value
2. It provides the source material for the AI-assistance section of the README

Updated as the build progresses. Honest, specific, not promotional.

---

## Tools used

| Tool | Used for |
|------|----------|
| **Claude Code (Opus 4.7, 1M context)** | Primary development environment. All file edits, code generation, corpus generation, web research, planning conversations. Run on Claude Max subscription. |
| **Web search** | Researching current best practices for LLM evaluation, OpenRouter capabilities, map-reduce summarization patterns, anti-AI-slop techniques, B2B interview transcript conventions, public corpora structure |
| **Context7 MCP** | (Reserved for Phase 4) Library documentation lookup for OpenAI SDK, Pydantic, OpenRouter — to avoid relying on training-data knowledge that may be stale |

---

## Workflow philosophy

The project is being built using a deliberate AI-augmented workflow rather than a "vibe-coded" one. The distinction:

- **Vibe-coded**: prompt → code → ship. AI generates the answer; human accepts.
- **AI-augmented**: human sets the strategy, AI does the labour of research and generation, human validates each stage before proceeding to the next.

Concretely, this looks like:

1. Plan in conversation before any code or content is written
2. Reach explicit alignment on architecture, eval framework, corpus design before generation begins
3. Use AI for research where training data may be stale (web search + MCP docs)
4. Use AI for content generation where labour is the bottleneck (corpus, draft code)
5. Validate at each phase boundary before proceeding

---

## Build phases and AI usage by phase

### Phase 0 — Scoping artifacts

AI used for:
- Drafting `docs/architecture.md`, `docs/corpus-design.md`, `docs/evaluation.md` based on conversational alignment with the project lead
- Web research on the eval-driven-development discourse (Hamel Husain, Eugene Yan), synthetic eval corpus design, OpenRouter structured outputs

Human judgment on:
- Architecture choice (map-reduce over context stuffing)
- Eval framework structure (three tiers vs pure EDD vs pure post-hoc)
- Decision to write Phase 0 docs as committable artifacts rather than internal scratch
- Decision that strategy / positioning content stays gitignored, methodology content is committed openly

Notable research finding that shaped the approach: Hamel Husain's [pushback on pure eval-driven development](https://hamel.dev/blog/posts/evals-faq/should-i-practice-eval-driven-development.html) (*"You can't anticipate what will break. Write evaluators for errors you discover, not errors you imagine"*). Without that surfacing, the original plan would have been pure EDD. The three-tier framework is the synthesis.

### Phase 1 — Corpus generation

AI used for:
- Generating all 101 documents directly in the Claude Code session (Opus 4.7) rather than via API
- Per-doc planning: type, length, themes, persona, stylistic notes
- Anti-AI-slop technique application during generation (banned vocabulary, no em dashes, sentence-length variation, persona rotation)
- Cross-doc continuity threading (recurring characters, named entities, narrative arcs)
- Web research on B2B interview transcript conventions, public corpus structures (Enron), anti-slop techniques, available "humanize" skills

Human judgment on:
- Decision to align corpus to the brief's 5 explicit doc types (rather than letting AI default to "internal memos")
- Deliberate difficulty mechanics: theme overlap, implicit themes, negation distractors, near-duplicates, variable salience, distractor noise
- Sealed manifest discipline (corpus first, manifest declared before extraction tool exists, extraction blind to manifest)
- Validation of sample docs before batching (8 samples + iteration → 92 more in batches)
- Filename variety to demonstrate tool is glob-driven, not name-driven

Notable research finding: investigated existing skills (`hamelsmu/generate-synthetic-data`, `lguz/humanize-writing-skill`) and decided not to install — the techniques those skills package are now explicit in the generation template, no install overhead.

Anti-slop rules applied during generation:
- No em dashes (single strongest AI tell)
- Banned vocabulary list (delve, tapestry, leverage, robust, comprehensive, navigate, seamless, pivotal, testament, crucial, ever-evolving, multifaceted)
- No parallel negation ("not X, but Y"), no tricolons, no mirror structures, no rhetorical Q+A
- Sentence length variation (mix 5-word and 30-word, never three similar in a row)
- Specific verifiable details (real-feeling names, dollar amounts, dates, quoted phrases)
- Persona injection per doc (~15 named authors with distinct voices, rotated across docs)
- Format mimicry (date headers in meeting notes, signature lines in emails, speaker labels and disfluencies in transcripts)
- Imperfections deliberately preserved (half-quotes, abbreviations, parenthetical asides, occasional incomplete sentences)

### Phase 2 — Eval framework

AI used for:
- Drafting Pydantic schemas (`src/schemas.py`), metric implementations (`eval/metrics.py`), grader orchestration (`eval/grader.py`), CLI (`eval/__main__.py`)
- Generating `eval/fixtures/fake_good.json` from the manifest (script-driven so citations stay aligned with `expected_docs`) and hand-crafting `eval/fixtures/fake_bad.json` to inject specific named failures
- Writing `tests/test_eval_fixtures.py` to assert the eval distinguishes good from bad

Human judgment on:
- Three-tier framework structure (decided in Phase 0, implemented here)
- Threshold values in `eval/thresholds.yaml` (committed in Phase 0, before fake_good existed; fake_good was hand-sized to clear them, not the other way around)
- Distractor handling design: aliases-based text matching plus citation-to-pure_noise as triggers (rather than requiring the manifest to grow a hand-curated FP rule set per distractor)
- Scope discipline: did NOT add a `tier_3` implementation — Tier 3 is defined as post-hoc and gets populated after Phase 6's real run

Validation done before declaring Phase 2 complete:
- `pytest` passes with no API keys set (CI-mode contract)
- `python -m eval --report eval/fixtures/fake_good.json` returns Overall PASS
- `python -m eval --report eval/fixtures/fake_bad.json` returns Overall FAIL with the expected metric names in the failure list (citation_hallucination_rate, all three theme_recall, doc_coverage, false_positive_rate_on_distractors)
- The thresholds were not retrofitted to the fixture; the fixture was sized to the thresholds

### Phase 3 — project skeleton

AI used for: drafting `pyproject.toml` (deps + ruff + mypy + pytest config), `Makefile`, `.env.example`, `config.yaml` template, `[tool.ruff.lint]` rule selection.

Human judgment on: dependency choice (no LangChain, no LlamaIndex confirmed), strict-mypy as default, line-length 110.

### Phase 4 — core pipeline

AI used for:
- Drafting all of `src/`: providers (`base.py`, `mock.py`, `openrouter.py`), `extract.py` / `aggregate.py` / `synthesize.py`, `pipeline.py` (bounded async, defensive citation stripping), `output.py` (Markdown + JSON), `cost.py`, `cache.py`, `config.py`, `cli.py`, `analyze_docs.py` shim, `prompts.py`
- Cross-checking the OpenAI SDK structured-outputs API against current docs via Context7 MCP (knowledge cutoff was January 2026; OpenAI SDK was at 2.32 by April). Confirmed `client.chat.completions.parse(response_format=PydanticModel)` and `AsyncOpenAI(base_url=...)` are the current patterns.
- Designing the wire/domain schema split: `PerDocExtractPayload` (LLM-facing, no defaults so OpenAI strict mode accepts the schema) wrapped into `PerDocExtract` (with source_file pinned by the pipeline)

Human judgment on:
- Pipeline-level enforcement of the `eval/manifest.yaml` import boundary (extraction code MUST NOT import the manifest — checked by reviewing imports, not just promised)
- Decision to defensively strip unknown citations in `pipeline.py` rather than let them flow to the report (Tier 1 hard constraint protection at the code layer, not just the eval)
- Decision to make the `MockProvider` produce schema-valid output that passes Tier 1 — proves the pipeline structure works without needing API access for grading

### Phase 5 — tests

AI used for: drafting `tests/test_schemas.py`, `test_mock_provider.py`, `test_cost.py`, `test_pipeline_e2e.py`, `test_output.py`, `test_extract_aggregate.py`, `test_openrouter_smoke.py` (`@pytest.mark.expensive`).

Human judgment on:
- Decision to make `test_pipeline_e2e.py` assert that the full mock pipeline passes Tier 1 (not just runs to completion) — ties the test suite to the eval framework
- Decision to mark the live-API test `expensive` and skip by default

### Phase 6 — real run + Tier 3 error analysis

AI used for: running the pipeline against the corpus via OpenRouter, grading the output, inspecting failed metrics, broadening the manifest aliases based on observed model phrasing.

Human judgment on:
- The crucial discipline call: the first run had 0% primary theme recall because the model used different theme names (e.g. "Pricing Competition and Pressure" vs canonical "Pricing pressure on renewals"). The honest fix was to widen the eval's matching vocabulary (aliases) — search vocabulary, not ground truth. The expected_docs lists are unchanged. Documented transparently in Tier 3.
- Decision NOT to lower thresholds when the model didn't hit them. `doc_coverage = 0.43` against the 0.75 threshold is documented as a known gap with a specific mitigation ("larger model" or "chain-of-thought citations"), not papered over.
- Decision to commit two runs (`report.json` + `report_run_b.json`) and report the consistency Jaccard as a real metric, not an afterthought.

Notable Tier 3 findings (full detail in `eval/thresholds.yaml`):
1. `doc_coverage` capped at ~0.43: gpt-4o-mini emits ~5 citations per theme regardless of prompting
2. `citation_precision` 0.58: docs touch multiple themes; strict per-theme precision penalises legitimate cross-theme citations
3. `consistency_jaccard` 0.625 vs 0.65 threshold: theme phrasing varies between runs at default temperature
4. Theme name variance broke substring matching: mitigated by broader aliases, not by lowering the bar

### Phase 7 — README

AI used for: drafting `README.md` (project overview, run instructions, CLI reference, architecture summary, prompt strategy, eval framework with reference scores table, honest limitations, "what I'd change for production" list).

Human judgment on:
- Reference scores table that shows the honest pass/fail picture, not just the wins
- "Honest limitations" section that mirrors the Tier 3 findings rather than burying them
- "What I'd change for production" list that reflects substantive engineering thought, not generic platitudes

### Phase 8 — Docker + final pass

AI used for: drafting `Dockerfile` (two-stage build, slim Python base, non-root user, deps cached separately from source) and `.dockerignore`.

Human judgment on:
- Decision to keep the runtime image lean: only `src/`, `eval/`, `input_docs/`, `config.yaml`, the entry shim. No tests, no docs.
- Decision to default to mock mode if no API key is passed (so `docker run doc-insight:dev` does something useful out of the box, no surprises).
- Documented permission gotcha in the README (output mount needs uid 1000 writability) rather than papering over it.

Smoke verified: build cleanly, mock-mode produces same output as native (~0.2s), real-mode against OpenRouter completes (~136s vs 64s native — container overhead).

---

## What AI did NOT do

- Decide the architecture
- Decide the eval framework structure
- Decide the corpus scenario or theme distribution
- Decide what counts as "good" output
- Decide what to omit (no frontend, no DB, no RAG, no orchestration framework)
- Set the timeline or pace

These are human-judgment decisions. AI did the labour of researching options, drafting documents, generating content, and writing code. The strategic and architectural calls are not AI-generated.

---

## Honest limitations of this approach

- **AI tends to settle into patterns.** Without deliberate variation discipline (per-doc spec cards, persona rotation, banned-vocabulary lists), 100 documents generated by AI will read as one author. The corpus design doc and the anti-slop rules above are how this is mitigated, but the mitigation requires active human attention. Without it, the corpus would have been visibly homogeneous.
- **AI tends to generate plausible-sounding content even when wrong.** During corpus generation, named entities, dates, and dollar amounts had to be checked for cross-document consistency manually. AI is not reliable at maintaining a coherent fictional world without explicit reminders.
- **AI tends to overcomplicate.** Without deliberate scope discipline, the project would have grown to include a frontend, a database, vector embeddings, an orchestration framework, and likely several other things the brief did not ask for. The "what we deliberately do not include" sections in the architecture and corpus-design docs are the deliberate counterweight.
- **AI is not reliably calibrated to its own confidence.** Throughout the build, AI presented options with reasoning and the project lead chose between them. Treating any AI-generated recommendation as definitive without independent reasoning would be a mistake. The conversational pattern was: AI proposes options + reasoning, human chooses, AI implements.
- **AI is reliable at generating individual artifacts and unreliable at maintaining coherence across many artifacts**. The cross-document continuity in the corpus required explicit tracking and manual cross-referencing during generation. Without that, the corpus would have had inconsistent named entities (e.g. "Marcus Tanaka" and "Lewis Tanaka" appearing as different people from different document — which did happen and was caught and corrected).

---

## What this project deliberately does NOT use

- **No LangChain, LlamaIndex, or other LLM orchestration framework.** Direct OpenAI SDK + Pydantic + httpx is the entire LLM-related stack. The map-reduce loop is ~50 lines of explicit Python, fully understood and inspectable.
- **No "agent" framework.** Each LLM call is a single structured invocation with a typed response. No autonomous loops, no tool-using agents.
- **No fine-tuning or custom models.** Off-the-shelf models via OpenRouter, with prompt engineering and structured output schemas as the only tuning surface.

These are deliberate choices in service of transparency and supportability. They reflect the brief's evaluation criterion ("readable, structured, maintainable without being overbuilt") and the principle that the harness around the model matters more than the model itself.

---

## What a reviewer should know

The corpus you're seeing was generated by AI but designed by hand. The architecture you're seeing was decided by hand and implemented with AI assistance. The evaluation framework you're seeing was researched, then synthesised by hand, then expressed as code with AI assistance.

If you read the code and find it generic, that's a fair criticism — the AI did the typing. If you read the architecture and corpus design and find them generic, that's a stronger criticism — those are where the project's actual judgment lives.

The work that distinguishes a serious AI-augmented project from a vibe-coded one is in the deliberate choices: what to omit, where to apply discipline, when to push back on AI suggestions, where to verify rather than accept. Those are the decisions documented across the `docs/` directory.
