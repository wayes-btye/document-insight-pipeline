# AI Assistance Note

How AI was used in building this project. Honest, specific, not promotional. The brief asks for this; this is also the source material for the AI-assistance section of the README.

---

## Tools used

| Tool | Used for |
|------|----------|
| **Claude Code (Opus 4.7, 1M context)** | Primary development environment. All file edits, code generation, corpus generation, web research, planning conversations. Run on Claude Max subscription. |
| **Web search** | Researching current best practices for LLM evaluation, OpenRouter capabilities, map-reduce summarization patterns, anti-AI-slop techniques, B2B interview transcript conventions, public corpora structure. |
| **Context7 MCP** | Library documentation lookup for the OpenAI Python SDK (used in Phase 4 to verify the current `chat.completions.parse(response_format=PydanticModel)` pattern, since the SDK had moved to v2.x past my January 2026 training cutoff). |
| **`code-reviewer` subagent** | Independent review of the pipeline at the end of Phase 8 to catch issues a single-author build misses. Findings drove the multi-model compatibility rewrite, the prompt-injection delimiter change, and the `.env` loader fix. |

---

## Workflow philosophy

The project is built using a deliberate AI-augmented workflow rather than a "vibe-coded" one. The distinction:

- **Vibe-coded**: prompt → code → ship. AI generates the answer; human accepts.
- **AI-augmented**: human sets the strategy, AI does the labour of research and generation, human validates each stage before proceeding to the next.

Concretely, this looked like:

1. Plan in conversation before any code or content is written
2. Reach explicit alignment on architecture, eval framework, corpus design before generation begins
3. Use AI for research where training data may be stale (web search + Context7)
4. Use AI for content generation where labour is the bottleneck (corpus, draft code)
5. Validate at each phase boundary before proceeding
6. Run an independent review pass (subagent) to catch issues that single-author iteration misses

---

## Build phases and AI usage by phase

### Phase 0 — Scoping artifacts

AI used for:
- Drafting `docs/architecture.md`, `docs/corpus-design.md`, `docs/evaluation.md`, `docs/decisions.md` based on conversational alignment with the project lead
- Web research on the eval-driven-development discourse (Hamel Husain, Eugene Yan), synthetic eval corpus design, OpenRouter structured outputs

Human judgment on:
- Architecture choice (map-reduce over context stuffing or RAG or agentic search)
- Eval framework structure (three tiers vs pure EDD vs pure post-hoc)
- Decision to write Phase 0 docs as committable artifacts rather than internal scratch
- Decision that strategy/positioning content stays gitignored, methodology content is committed openly

Notable research finding that shaped the approach: Hamel Husain's [pushback on pure eval-driven development](https://hamel.dev/blog/posts/evals-faq/should-i-practice-eval-driven-development.html) — *"You can't anticipate what will break. Write evaluators for errors you discover, not errors you imagine."* Without that surfacing, the original plan would have been pure EDD. The three-tier framework is the synthesis.

### Phase 1 — Corpus generation

AI used for:
- Generating all 101 documents directly in the Claude Code session (Opus 4.7) rather than via API
- Per-doc planning: type, length, themes, persona, stylistic notes
- Anti-AI-slop technique application during generation (banned vocabulary, no em dashes, sentence-length variation, persona rotation)
- Cross-doc continuity threading (recurring characters, named entities, narrative arcs)
- Web research on B2B interview transcript conventions, public corpus structures (Enron), anti-slop techniques

Human judgment on:
- Decision to align corpus to the brief's 5 explicit doc types (rather than letting AI default to "internal memos")
- Deliberate difficulty mechanics: theme overlap, implicit themes, negation distractors, near-duplicates, variable salience, distractor noise
- Sealed manifest discipline (corpus first, manifest declared before extraction tool exists, extraction blind to manifest)
- Validation of sample docs before batching (8 samples + iteration → 92 more in batches)
- Filename variety to demonstrate the tool is glob-driven, not name-driven

Notable research: investigated existing skills (`hamelsmu/generate-synthetic-data`, `lguz/humanize-writing-skill`) and decided not to install — the techniques those skills package are now explicit in the generation template, no install overhead.

Anti-slop rules applied during generation:
- No em dashes (the single strongest AI tell)
- Banned vocabulary list (delve, tapestry, leverage, robust, comprehensive, navigate, seamless, pivotal, testament, crucial, ever-evolving, multifaceted)
- No parallel negation ("not X, but Y"), no tricolons, no mirror structures, no rhetorical Q+A
- Sentence length variation (mix 5-word and 30-word, never three similar in a row)
- Specific verifiable details (real-feeling names, dollar amounts, dates, quoted phrases)
- Persona injection per doc (~15 named authors with distinct voices, rotated across docs)
- Format mimicry (date headers in meeting notes, signature lines in emails, speaker labels and disfluencies in transcripts)
- Imperfections deliberately preserved (half-quotes, abbreviations, parenthetical asides, occasional incomplete sentences)

### Phase 2 — Eval framework

AI used for:
- Drafting Pydantic schemas (`src/schemas.py`), metric implementations (`eval/metrics.py`), grader (`eval/grader.py`), CLI (`eval/__main__.py`)
- Generating `eval/fixtures/fake_good.json` from the manifest (script-driven so citations stay aligned with `expected_docs`) and hand-crafting `eval/fixtures/fake_bad.json` to inject specific named failures
- Writing `tests/test_eval_fixtures.py` to assert the eval distinguishes good from bad

Human judgment on:
- Three-tier framework structure (decided in Phase 0, implemented here)
- Threshold values in `eval/thresholds.yaml` (committed in Phase 0 before fake_good existed; fake_good was hand-sized to clear them, not the other way around)
- Distractor handling design: alias-based text matching plus citation-to-pure_noise as triggers, rather than a hand-curated FP rule set per distractor
- Scope discipline: did NOT add a `tier_3` implementation — Tier 3 is defined as post-hoc and gets populated after Phase 6's real run

Validation done before declaring Phase 2 complete: pytest passes with no API keys; `python -m eval --report fake_good.json` PASSes; `python -m eval --report fake_bad.json` FAILs with the expected metric names; thresholds were not retrofitted to the fixture.

### Phase 3 — Project skeleton

AI used for: drafting `pyproject.toml` (deps + ruff + mypy + pytest config), `Makefile`, `.env.example`, `config.yaml`, the `[tool.ruff.lint]` rule selection.

Human judgment on: dependency choice (no LangChain, no LlamaIndex), strict-mypy as default, line-length 110.

### Phase 4 — Core pipeline

AI used for:
- Drafting all of `src/`: providers (`base.py`, `mock.py`, `openrouter.py`), `extract.py` / `aggregate.py` / `synthesize.py`, `pipeline.py` (bounded async, defensive citation stripping), `output.py` (Markdown + JSON), `cost.py`, `cache.py`, `config.py`, `cli.py`, `analyze_docs.py` shim, `prompts.py`
- Cross-checking the OpenAI SDK structured-outputs API against current docs via Context7 MCP. Knowledge cutoff was January 2026; the SDK had moved to v2.x by April. Confirmed `client.chat.completions.parse(response_format=PydanticModel)` and `AsyncOpenAI(base_url=...)` are the current patterns.
- Designing the wire/domain schema split: `PerDocExtractPayload` (LLM-facing, no defaults so OpenAI strict mode accepts the schema) wrapped into `PerDocExtract` (with source_file pinned by the pipeline)

Human judgment on:
- Pipeline-level enforcement of the `eval/manifest.yaml` import boundary: extraction code MUST NOT import the manifest. Verified by inspection, not just promised.
- Decision to defensively strip unknown citations in `pipeline.py` rather than let them flow to the report (Tier 1 hard-constraint protection at the code layer, not just at eval time)
- Decision to make `MockProvider` produce schema-valid output that passes Tier 1 — proves the pipeline structure works without API access for grading

### Phase 5 — Tests

AI used for: drafting `tests/test_schemas.py`, `test_mock_provider.py`, `test_cost.py`, `test_pipeline_e2e.py`, `test_output.py`, `test_extract_aggregate.py`, `test_openrouter_smoke.py` (`@pytest.mark.expensive`).

Human judgment on:
- Decision to make `test_pipeline_e2e.py` assert that the full mock pipeline passes Tier 1 (not just runs to completion) — ties the test suite to the eval framework
- Decision to mark the live-API test `expensive` and skip by default

### Phase 6 — Real run + Tier 3 error analysis

AI used for: running the pipeline against the corpus via OpenRouter, grading the output, inspecting failed metrics, broadening the manifest aliases based on observed model phrasing.

Human judgment on:
- The crucial discipline call: the first run had 0% primary theme recall because the model used different theme names (e.g. "Pricing Competition and Pressure" vs canonical "Pricing pressure on renewals"). The honest fix was to widen the eval's matching vocabulary (aliases) — search vocabulary, not ground truth. The `expected_docs` lists are unchanged. Documented transparently in Tier 3.
- Decision NOT to lower thresholds when a model didn't hit them. Each Tier 2 miss is documented as a Tier 3 finding with a specific mitigation, not papered over.
- Decision to commit two runs with the consistency Jaccard score, not just one.

Tier 3 findings populated in `eval/thresholds.yaml`:
1. `doc_coverage` under target — gpt-4o-mini emits ~5 citations per theme regardless of prompting; closes with a larger reduce-stage model (sonnet-4.5 already clears the threshold)
2. `citation_precision` under target — many docs touch multiple themes, and per-theme strict precision penalises legitimate cross-theme citations
3. `theme_name_variance_breaks_substring_match` — substring matching is brittle to natural-language variation; mitigated by broader aliases, embedding-based matching is the production fix
4. `run_to_run_theme_variance` — at default temperature theme phrasing varies across runs; mitigated by temperature 0.3 default
5. `medium_theme_recall_inconsistent` — the model sometimes generalises a Relay-specific theme to "Strategic Partnerships and Collaborations", which substring matching misses

### Phase 7 — README, AI-assistance, decisions doc

AI used for: drafting `README.md` (project overview, run instructions, CLI reference, architecture summary, prompt strategy, eval framework with multi-model comparison table, honest limitations, "what I'd change for production"); `docs/decisions.md` (top-level architectural trade-offs with rejected alternatives like RAG, context stuffing, agentic search).

Human judgment on:
- Multi-model comparison table that shows the honest pass/fail picture across 5 models, not just the wins
- "Honest limitations" section that mirrors the Tier 3 findings rather than burying them
- Pointing to `docs/decisions.md` from the README as the first thing a reviewer should read

### Phase 8 — Docker, multi-model verification, CI, code review, final pass

AI used for:
- `Dockerfile` (two-stage build, slim Python base, non-root user, deps cached separately from source) and `.dockerignore`
- `.github/workflows/ci.yml` (ruff + mypy strict + pytest on push/PR, no API key needed)
- Multi-model comparison runs across `gpt-4o-mini`, `gpt-4o`, `claude-3-5-haiku`, `claude-sonnet-4.5`, `gemini-2.0-flash-001`. Outputs in `eval/results/comparison/`.
- Independent code review by the `code-reviewer` subagent at the end of the build (separate context window, no benefit-of-the-doubt)

Human judgment on:
- Catching the multi-model bug from real testing: a `claude-3-5-haiku` run failed with "Invalid JSON: I apologize, but the prompt..." — a text refusal getting parsed as JSON. The reviewer agent confirmed the root cause: `chat.completions.parse()` is OpenAI-native; non-OpenAI models on OpenRouter return JSON in `content`, not in the structured-output `parsed` field. Fix is in `src/providers/openrouter.py`: model-prefix dispatch between strict-parse path (OpenAI) and `json_object` mode + manual parse path (everything else).
- Acting on reviewer findings: UUID-tagged delimiters around document content in the map prompt + system-prompt notice that document content is untrusted USER DATA (prompt-injection hardening); fix to `_load_dotenv` to handle inline comments and quoted values; `docs_failed` count surfaced in `ReportMetadata` so silent failures don't disappear; `false_positive_rate_on_distractors` refactored from two parallel zip-loops to a single tuple loop.
- Temperature default: started at 0.0 for reproducibility, but observed worse `doc_coverage` and `theme_recall` because the model gets too conservative. Settled on 0.3 — keeps most of the consistency benefit without crippling pattern-matching. Documented in `docs/decisions.md`.
- Decision to keep Docker runtime image lean (only `src/`, `eval/`, `input_docs/`, `config.yaml`, the entry shim — no tests, no docs)
- Default to mock mode when no API key is passed (`docker run doc-insight:dev` does something useful out of the box)

Smoke verified: builds clean, mock-mode produces same output as native (~0.2s), real-mode against OpenRouter completes (~136s vs 64s native — container overhead). CI workflow runs lint + typecheck + tests; tests are mock-only so no secret needs to live in GitHub Actions.

---

## What AI did NOT do

- Decide the architecture (map-reduce over the alternatives)
- Decide the eval framework structure (three tiers, sealed manifest)
- Decide the corpus scenario, theme distribution, or difficulty mechanics
- Decide what counts as "good" output (Tier 1/2 thresholds were pre-committed by the project lead)
- Decide what to omit (no frontend, no DB, no RAG, no orchestration framework)
- Decide when to commit or push, or what visibility the repo should have
- Set the timeline or pace

These are human-judgment decisions. AI did the labour of researching options, drafting documents, generating content, writing code, and running comparisons. The strategic and architectural calls are not AI-generated.

---

## Honest limitations of this approach

- **AI tends to settle into patterns.** Without deliberate variation discipline (per-doc spec cards, persona rotation, banned-vocabulary lists), 100 documents generated by AI will read as one author. The corpus design doc and the anti-slop rules are how this is mitigated, but the mitigation requires active human attention.
- **AI tends to generate plausible-sounding content even when wrong.** During corpus generation, named entities, dates, and dollar amounts had to be checked for cross-document consistency. AI is not reliable at maintaining a coherent fictional world without explicit reminders. Example: "Marcus Tanaka" and "Lewis Tanaka" briefly appeared as different people across two documents — caught and corrected.
- **AI tends to overcomplicate.** Without deliberate scope discipline, the project would have grown to include a frontend, a database, vector embeddings, an orchestration framework, and several other things the brief did not ask for. The "what we deliberately do not include" sections in the architecture and decisions docs are the deliberate counterweight.
- **AI is not reliably calibrated to its own confidence.** AI presented options with reasoning and the project lead chose between them. Treating any AI-generated recommendation as definitive without independent reasoning would be a mistake.
- **AI is reliable at generating individual artifacts and unreliable at maintaining coherence across many artifacts.** Documentation drift across phases is a real risk. The Phase 8 cleanup pass involved reading every doc end-to-end to fix inconsistencies that accumulated as the build progressed (reference scores quoted in different places, phase status that lagged the actual state, etc.).
- **Single-author AI builds miss things a reviewer catches.** The multi-model compatibility bug, prompt-injection delimiter weakness, and `.env` loader edge cases were all caught by the independent `code-reviewer` subagent run, not by the iterating author. That's why the review pass exists.

---

## What this project deliberately does NOT use

- **No LangChain, LlamaIndex, or other LLM orchestration framework.** Direct OpenAI SDK + Pydantic + httpx is the entire LLM-related stack. The map-reduce loop is ~50 lines of explicit Python, fully understood and inspectable.
- **No "agent" framework.** Each LLM call is a single structured invocation with a typed response. No autonomous loops, no tool-using agents.
- **No fine-tuning or custom models.** Off-the-shelf models via OpenRouter, with prompt engineering and structured-output schemas as the only tuning surface.
- **No RAG / embeddings / vector database.** The task is summarisation of a known corpus, not retrieval over an unknown one. Documented in `docs/decisions.md`.

These are deliberate choices in service of transparency and supportability. They reflect the brief's evaluation criterion ("readable, structured, maintainable without being overbuilt") and the principle that the harness around the model matters more than the model itself.

---

## What a reviewer should know

The corpus you're seeing was generated by AI but designed by hand. The architecture you're seeing was decided by hand and implemented with AI assistance. The evaluation framework was researched, then synthesised by hand, then expressed as code with AI assistance.

If you read the code and find it generic, that's a fair criticism — AI did the typing. If you read the architecture (`docs/architecture.md`), the decisions (`docs/decisions.md`), and the corpus design (`docs/corpus-design.md`) and find them generic, that's a stronger criticism — those are where the project's actual judgment lives.

The work that distinguishes a serious AI-augmented project from a vibe-coded one is in the deliberate choices: what to omit, where to apply discipline, when to push back on AI suggestions, where to verify rather than accept, when to bring in an independent reviewer to catch what the iterating author missed. Those are the decisions documented across `docs/`.
