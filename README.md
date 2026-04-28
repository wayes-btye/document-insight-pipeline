# Document Insight Pipeline

A small Python tool that reads a folder of `.txt` business documents, extracts structured insights via an LLM, and produces an executive-readable summary report (Markdown + JSON) with grounded citations.

```
input_docs/*.txt  ──►  map (per-doc extract)  ──►  reduce (cluster + cite)  ──►  synthesise (narrative)  ──►  summary_report.md / .json
```

Map-reduce architecture, no orchestration framework, mock provider as a first-class option for keyless runs, and a three-tier evaluation harness built **before** the tool itself.

---

## Run instructions

### 1. Install

```bash
git clone <this-repo> document-insight-pipeline
cd document-insight-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

(Or `make install-dev` if you have a `.venv` already.)

### 2. Mock mode — no API key required

Activate the venv first so the bare `python` works (`source .venv/bin/activate`), or call `.venv/bin/python` directly. The rest of this README uses the bare `python` form.

```bash
python -m src.cli --input_dir ./input_docs --output ./summary_report.md --mock
# or via the brief's example shim:
python analyze_docs.py --input_dir ./input_docs --output ./summary_report.md --mock
```

Produces `summary_report.md` and `summary_report.json` in ~0.2s with the deterministic keyword-driven `MockProvider`. Useful for smoke-testing the pipeline without burning tokens.

### 3. Real run via OpenRouter

```bash
cp .env.example .env  # edit to add OPENROUTER_API_KEY
python -m src.cli --input_dir ./input_docs --output ./summary_report.md --model openai/gpt-4o-mini
```

Or change the model:

```bash
python -m src.cli --input_dir ./input_docs --output ./summary_report.md --model anthropic/claude-3-5-haiku
```

A reference run against the committed 101-doc corpus took **64 seconds** and cost **$0.025** with `openai/gpt-4o-mini`. Sample output is in [`examples/sample_summary_report.md`](examples/sample_summary_report.md).

### 4. Evaluate any report

```bash
python -m eval --report examples/sample_summary_report.json
```

The eval prints per-tier scores and exits non-zero with `--strict` on any failure. See [`docs/evaluation.md`](docs/evaluation.md) for the framework.

### 5. Run the test suite

```bash
make test         # mock-only, no API key required
make test-all     # also runs `@pytest.mark.expensive` against the real API
```

22 tests, ~1 second locally.

### 6. Docker

```bash
docker build -t doc-insight:dev .

# Mock mode, no API key needed; output stays in the container by default
docker run --rm -v "$PWD/out:/out" doc-insight:dev \
  --input_dir input_docs --output /out/summary --mock

# Real mode, pass the key as an env var (don't bake it into the image)
docker run --rm -v "$PWD/out:/out" -e OPENROUTER_API_KEY \
  doc-insight:dev \
  --input_dir input_docs --output /out/summary --model openai/gpt-4o-mini
```

The image runs as a non-root user (`app`). The output mount needs to be writable by uid 1000 — `chmod 777 ./out` on the host before mounting, or chown the directory to your local user.

---

## CLI reference

```
python -m src.cli [options]

  --input_dir PATH       directory of .txt files (default: ./input_docs)
                         --input-dir is also accepted
  --output PATH          output path; extension is replaced per --format
  --model STR            OpenRouter model id (default from config.yaml)
  --concurrency N        bounded async concurrency for the map stage (default 5)
  --format CHOICE        md | json | both (default both)
  --mock                 use the MockProvider; no API key needed
  --config PATH          path to config.yaml (default ./config.yaml)
  --cache | --no-cache   override cache.enabled in config
  --quiet | --verbose    log volume
```

`config.yaml` is the source of truth for defaults (model, concurrency, output format, cache toggle, per-1M-token price table). CLI flags override.

---

## Architecture

Three explicit stages, each with a typed contract between them:

| Stage | Module | What it does | LLM calls |
|-------|--------|--------------|-----------|
| Map | `src/extract.py` | Read one document, return a `PerDocExtractPayload`. Source filename is pinned by the pipeline, not the model — the model cannot hallucinate which file it just read. | 1 per doc, async with bounded concurrency |
| Reduce | `src/aggregate.py` | Cluster paraphrased themes across all per-doc extracts, attach citations, derive salience. Operates over compact JSON, not raw document text. | 1 |
| Synthesise | `src/synthesize.py` | Produce the executive-readable narrative (executive summary + assumptions + limitations) from `AggregatedFindings`. | 1 |
| Assemble | `src/pipeline.py` | Compose stages, build `SummaryReport`, defensively strip any citations to filenames not in the input dir before they reach the output. | 0 |

**Why map-reduce, not single-shot context stuffing.** Citations stay accurate because the model never sees more than one document at a time during extraction. Costs scale linearly. Per-doc failures don't break the whole run. Per-doc extracts are inspectable, diff-able, and unit-testable. Full discussion in [`docs/architecture.md`](docs/architecture.md).

**LLM provider.** `OpenAI` Python SDK pointed at OpenRouter's OpenAI-compatible base URL. Model selection is a config string. `MockProvider` is a first-class implementation, not a hack — every code path that calls an LLM works against it with no API key, the eval suite runs in CI without credentials, and the full pipeline produces a real (if simplistic) report end-to-end.

**No LangChain, no LlamaIndex, no agent framework.** The map-reduce loop is ~50 lines of explicit Python. Every LLM call is a single structured invocation with a typed Pydantic response.

---

## Prompt strategy

Three short prompts in [`src/prompts.py`](src/prompts.py).

- **Map**: extract themes, insights, risks, opportunities, actions, optional notes. Hard rules: don't invent content; don't surface admin noise as themes; don't surface dismissed ideas as opportunities (negation discipline).
- **Reduce**: cluster paraphrases into 5-10 distinct themes; cite every supporting filename per theme; same negation/noise rules.
- **Synthesise**: 3-5 sentence executive summary plus assumptions and limitations. Hard rules: no platitudes ("strategic positioning", "evolving landscape"), no bullets in the summary.

The structured-output schema (Pydantic via `client.chat.completions.parse(response_format=...)`) is what enforces shape and required fields. The prompt's job is just to set the task and the constraints we care about.

---

## Evaluation framework

Three tiers, defended in [`docs/evaluation.md`](docs/evaluation.md). Built before the tool. All metrics run in CI without API keys.

| Tier | What it measures | Example metric |
|------|------------------|----------------|
| **Tier 1 — hard constraints** | Things that should never break, regardless of LLM. Pre-committed thresholds. | `citation_hallucination_rate ≤ 0` |
| **Tier 2 — synthetic capability** | What a competent map-reduce pipeline should achieve against a sealed manifest of planted themes (`eval/manifest.yaml`). | `primary_theme_recall ≥ 0.85`, `false_positive_rate_on_distractors ≤ 0.10` |
| **Tier 3 — discovered failures** | Specific gaps observed on the real run, with mitigations. Populated post-hoc, not pre-imagined. | See `eval/thresholds.yaml` `tier_3_discovered.findings` |

The Tier 3 split is deliberate, following Hamel Husain's pushback on pure eval-driven development: write evaluators for errors you discover, not errors you imagine.

### Reference scores

The committed reference run (`examples/sample_summary_report.{md,json}`) is `openai/gpt-4o-mini` with the default temperature of 0.3, against the full 101-doc corpus. **Tier 1 fully PASSes on every model we tried.** Tier 2 capability varies — see the comparison table below.

### Multi-model comparison

All five models were run end-to-end against the same corpus through the same pipeline. Persisted outputs in [`eval/results/comparison/`](eval/results/comparison). Scores rounded; `✓` = passes the Tier 2 threshold for that metric.

| Model | Time | Cost | Hi recall ≥0.85 | Med recall ≥0.70 | Lo recall ≥0.50 | Cite precision ≥0.90 | Doc coverage ≥0.75 | FP on distractors ≤0.10 |
|---|---|---|---|---|---|---|---|---|
| `openai/gpt-4o-mini` (default) | 113s | $0.026 | 0.75 | **1.00** ✓ | 0.67 ✓ | 0.44 | 0.25 | 0.00 ✓ |
| `openai/gpt-4o` | 75s | $0.430 | 0.75 | 0.00 | **1.00** ✓ | 0.69 | 0.53 | 0.00 ✓ |
| `anthropic/claude-3-5-haiku` | 112s | $0.240 | 0.50 | 0.33 | **1.00** ✓ | **0.88** | 0.35 | 0.00 ✓ |
| `anthropic/claude-sonnet-4.5` | 263s | $0.61 (est) | 0.75 | 0.67 | **1.00** ✓ | 0.79 | **0.86** ✓ | 0.00 ✓ |
| `google/gemini-2.0-flash-001` | 209s | $0.02 (est) | 0.75 | 0.67 | **1.00** ✓ | 0.70 | **0.77** ✓ | 0.00 ✓ |

Sonnet-4.5 has the best balanced profile (only model to pass `doc_coverage`); Gemini Flash is the value pick (passes `doc_coverage` at near-zero cost); Haiku has the highest `citation_precision` but lowest recall; gpt-4o-mini is fastest and cheapest but underperforms larger models on coverage. **No model hits all Tier 2 thresholds against the synthetic manifest** — the thresholds were not lowered to fit any one model. The persistent gap is `citation_precision`, which is partly a real model limitation and partly a substring-matching limitation in the eval's theme matcher; documented honestly as Tier 3 finding `citation_precision_under_target` in `eval/thresholds.yaml`.

(Note: the cross-model comparison runs were captured at temperature 0.0 for reproducibility; the committed reference output uses the new default of 0.3 — see "Temperature" in `docs/decisions.md` for why 0.3 not 0.0.)

Threshold rationale and Tier 3 findings in [`eval/thresholds.yaml`](eval/thresholds.yaml).

---

## Honest limitations

- **Tier 2 capability is partial against `gpt-4o-mini`**. `doc_coverage` and `citation_precision` underperform — the model emits ~5 citations per theme regardless of prompting. Larger models or a chain-of-thought "candidate citations" pre-step would close this. Documented in Tier 3.
- **Run-to-run consistency is borderline (Jaccard 0.625 vs 0.65 threshold)**. Default temperature is 1.0; setting `temperature=0` in production is the simple fix. Not done in this codebase to keep behaviour close to the SDK's defaults.
- **Theme matching uses substring overlap, not embeddings**. Transparent and explainable, but brittle to natural-language variation. The eval misses semantically-correct themes that don't share a substring with any alias. Mitigated in Phase 6 by broadening alias lists; production would use embedding-based matching.
- **Per-doc extraction loses cross-doc context**. Mitigated by the reduce stage operating over structured extracts, but a document that only makes sense relative to another will lose nuance.
- **Cost figures are indicative**. The price table in `config.yaml` is a snapshot; OpenRouter pricing changes. Update from `openrouter.ai/models` if it matters.
- **Synthetic corpus**. Buyer sentiment patterns are stylised. Real production runs would need to validate against a real-data sample before relying on the eval scores as a quality signal.
- **No PII handling**. The corpus is fictional; production would need redaction at ingest.

---

## What I'd change for production

The codebase is intentionally a CLI tool, not a service. To deploy internally:

- **Real response cache** (Redis with TTL + invalidation) instead of the dev-only file cache
- **Structured JSON logging** to stdout, parseable by Cloud Logging / Datadog
- **Metrics export** (OpenTelemetry: per-stage latency, token cost, retry counts, schema-validation failures)
- **Rate limiting** that respects upstream provider quotas, not just SDK retries
- **PII detection / redaction** at ingest
- **Schema versioning** for the structured outputs, with a migration story for old eval reports
- **Human-in-the-loop review** before reports go to stakeholders
- **Eval in production**: sampled spot-checks, drift monitoring against the manifest, alerting on Tier 1 regressions
- **Embedding-based theme matching** in the eval (replacing substring), with a per-theme similarity threshold
- **Per-tenant isolation** if multi-customer
- **Larger model for the reduce stage** (gpt-4o or claude-sonnet-4) to address `doc_coverage` and `citation_precision` gaps
- **Consensus across N runs** to address the consistency Jaccard gap (cheap insurance at low temperature)

---

## Project structure

```
.
├── analyze_docs.py            # top-level CLI shim (per the brief)
├── config.yaml                # default runtime config
├── .env.example               # OPENROUTER_API_KEY template
├── Makefile                   # install, test, lint, format, typecheck, eval, run
├── pyproject.toml             # deps + ruff + mypy + pytest config
│
├── src/
│   ├── cli.py                 # argparse entry, --mock, --concurrency, ...
│   ├── pipeline.py            # map → reduce → synthesise orchestrator
│   ├── extract.py             # map stage
│   ├── aggregate.py           # reduce stage
│   ├── synthesize.py          # synthesis stage
│   ├── output.py              # MD + JSON writers
│   ├── cost.py                # token counting + price table
│   ├── cache.py               # content-hash cache (dev-only by default)
│   ├── config.py              # config.yaml loader
│   ├── prompts.py             # all three prompts in one place
│   ├── schemas.py             # Pydantic contract
│   └── providers/
│       ├── base.py            # LLMProvider Protocol
│       ├── mock.py            # deterministic, keyword-driven, no API key
│       └── openrouter.py      # OpenAI SDK pointed at OpenRouter
│
├── eval/                      # the harness, sealed manifest, fixtures, results
│   ├── manifest.yaml          # ground-truth themes + expected_docs (locked)
│   ├── thresholds.yaml        # tier 1/2 thresholds + tier 3 discovered findings
│   ├── metrics.py             # per-metric implementations
│   ├── grader.py              # orchestrator
│   ├── __main__.py            # `python -m eval --report path`
│   ├── fixtures/              # fake_good.json + fake_bad.json (sanity checks)
│   └── results/               # persisted reference runs
│
├── input_docs/                # 101 fictional business documents (committed)
├── examples/                  # sample summary_report.md + .json
├── tests/                     # pytest suite
└── docs/                      # architecture, corpus design, eval, build plan, AI assistance
```

---

## AI assistance

This project was built using a deliberate AI-augmented workflow. [`docs/ai-assistance.md`](docs/ai-assistance.md) documents what AI did, what human judgment did, and the honest limitations of the approach. Briefly:

- All file edits, code generation, prompts, and the corpus were produced via Claude Code (Opus, 1M context) with active human direction
- Strategic decisions (architecture, eval framework, scope, what to omit) were human; AI did the labour of researching, drafting, and generating
- The corpus was generated by AI but designed by hand, with explicit anti-AI-slop techniques applied (banned vocabulary, no em dashes, persona rotation, deliberate imperfections, format mimicry)
- Web search and Context7 MCP were used to verify current OpenAI SDK patterns rather than relying on training-data knowledge

See [`docs/ai-assistance.md`](docs/ai-assistance.md) for the full account, including what AI did NOT do and the workflow philosophy.

---

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/decisions.md`](docs/decisions.md) | **Top-level decisions and trade-offs.** Why map-reduce over RAG / context stuffing / agentic search. Honest drawbacks of the chosen path. Table of every other architectural decision. **Read this first if you're reviewing.** |
| [`docs/architecture.md`](docs/architecture.md) | Map-reduce design, components, data shapes, deliberate exclusions |
| [`docs/corpus-design.md`](docs/corpus-design.md) | Fictional scenario, doc-type taxonomy, theme planting, deliberate difficulty mechanics |
| [`docs/evaluation.md`](docs/evaluation.md) | Three-tier framework, defence of synthetic approach, references |
| [`docs/build-plan.md`](docs/build-plan.md) | Phased plan and what's done at each phase |
| [`docs/ai-assistance.md`](docs/ai-assistance.md) | How AI was used, what human judgment did |

Suggested reading order for a reviewer: this README → `docs/decisions.md` → `docs/architecture.md` → `docs/evaluation.md` → `examples/sample_summary_report.md` → `eval/results/comparison/` → `src/` (start with `schemas.py`, then `prompts.py`, then `pipeline.py`).
