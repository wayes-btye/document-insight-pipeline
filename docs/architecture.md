# Architecture

## Purpose

A command-line tool that reads a directory of text documents, extracts structured insights using an LLM, aggregates across the corpus, and produces a business-facing summary report. Designed to be plausibly extensible into an internal business tool — not a throwaway script.

## High-level flow

```
input_docs/*.txt
        │
        ▼
┌────────────────────┐    Per-doc structured extraction
│   MAP STAGE        │    (one LLM call per document)
│                    │    Output: PerDocExtract with citation pinned
└─────────┬──────────┘
          │  list[PerDocExtract]
          ▼
┌────────────────────┐    Cluster + aggregate themes,
│   REDUCE STAGE     │    insights, risks, opportunities, actions.
│                    │    Reasons over structured extracts, not raw text.
└─────────┬──────────┘
          │  AggregatedFindings
          ▼
┌────────────────────┐    Final business-readable narrative
│   SYNTHESIS STAGE  │    + assumptions + limitations
│                    │    (one LLM call over compact aggregate)
└─────────┬──────────┘
          │
          ▼
   summary_report.md  +  summary_report.json
```

The corpus is processed in three explicit stages, each with a typed contract between them. This separation is the whole architecture — it's what makes citations reliable, costs predictable, and behaviour testable.

## Why map-reduce, not single-shot context stuffing

Modern context windows could fit ~100 short documents in a single prompt. We're not doing that, and the README will explain why:

1. **Citation accuracy degrades with context length.** Lost-in-the-middle is well-documented. If you stuff 100 docs and ask "which docs support theme X," the model will hallucinate citations. With per-doc extraction, the model only sees one doc per call — it cannot cite the wrong file because no other file is in scope.
2. **Production scaling.** A single-shot architecture works for 100 docs and breaks at 1000. Map-reduce scales linearly with corpus size and parallelises trivially.
3. **Cost predictability.** Each map call is small and cacheable by content hash. Re-running the reduce/synthesis stage during prompt iteration doesn't re-bill the per-doc extracts.
4. **Failure isolation.** If 3 of 100 docs fail extraction, the run continues and the report flags the gap. Single-shot fails atomically.
5. **Observability.** Per-doc structured outputs are inspectable, diff-able, and unit-testable. A 100-doc mega-prompt is a black box.

The README discusses when single-shot stuffing would be valid (small homogeneous corpus, no citation requirements) — showing judgment, not absolutism.

## Components

| Module | Responsibility |
|--------|---------------|
| `src/providers/` | LLM provider abstraction. `OpenRouterProvider` (real) + `MockProvider` (deterministic, no key required). One thin interface — `complete_structured(messages, schema) -> dict`. |
| `src/schemas.py` | Pydantic models. `PerDocExtract`, `Theme`, `Insight`, `Risk`, `Opportunity`, `Action`, `AggregatedFindings`, `SummaryReport`. Single source of truth — used for prompts, parsing, validation, and tests. |
| `src/extract.py` | Map stage. Reads one doc, calls provider with structured-output schema, returns `PerDocExtract` with `source_file` populated. |
| `src/aggregate.py` | Reduce stage. Reasons over `list[PerDocExtract]` (compact JSON), produces `AggregatedFindings` with theme clustering and citation collection. |
| `src/synthesize.py` | Synthesis stage. Takes `AggregatedFindings` and renders the executive-readable narrative report. |
| `src/pipeline.py` | Orchestrates map → reduce → synthesise. Async with bounded concurrency for the map stage. |
| `src/output.py` | Writes `summary_report.md` and `summary_report.json`. JSON includes token counts and cost estimates. |
| `src/cost.py` | Tracks token usage and estimates cost from a per-model price table. |
| `src/cache.py` | Content-hash cache for LLM responses. Disabled by default in production, enabled for dev iteration. |
| `src/cli.py` | `analyze_docs.py` entry point. Argparse, config-file loading, mock-mode flag. |

## LLM provider strategy

**OpenAI Python SDK pointed at OpenRouter.** OpenRouter is OpenAI-API-compatible, so we get the production-grade SDK (typed clients, async support, built-in retries) without committing to one model vendor. Model selection is a config string: `anthropic/claude-sonnet-4-5`, `openai/gpt-4o-mini`, `google/gemini-2.0-flash-exp`, etc.

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)
```

**Structured outputs are non-optional.** Every map and reduce call uses `response_format={"type": "json_schema", "json_schema": {"strict": True, ...}}`. Citations are required fields, not optional — the schema enforces grounding at the API boundary. Provider preferences include `require_parameters: true` so a model that doesn't support structured outputs fails fast rather than degrading silently to free-text.

**Mock provider is first-class, not a hack.** `MockProvider` produces deterministic, schema-valid outputs based on simple keyword heuristics over the input text. The full pipeline runs to completion against it with no API key, producing a real (if simplistic) report. This is what makes the eval suite runnable in CI and the project runnable for any reviewer without credentials.

**No LangChain, no LlamaIndex, no orchestration frameworks.** The map-reduce loop is ~50 lines of explicit Python. We understand exactly what runs and when.

## Concurrency, retries, caching

**Concurrency.** Map stage is async with `asyncio.Semaphore` bounded concurrency (default 5). Configurable via `config.yaml`. Reduce and synthesis are sequential single calls.

**Retries.** OpenAI SDK's built-in retry handles transient 429/5xx with exponential backoff. We layer `tenacity` on top for the structured-output validation case — if the model returns valid JSON that fails Pydantic validation, we retry with a corrective system message before giving up.

**Caching.** `src/cache.py` keys on `sha256(model + messages + schema)`. Hits return cached responses instantly with zero token cost. Default: disabled. Enable via `config.yaml` or `--cache` flag during development to avoid burning tokens iterating on the reduce/synthesis prompts. Documented as dev-only — production deployments would use a proper response cache (Redis) with TTLs.

## Data shapes

The full schema is in `src/schemas.py`. Sketch:

```python
class Theme(_Strict):
    name: str
    description: str
    citations: list[str] = Field(min_length=1)   # required, non-empty
    salience: Salience                           # high / medium / low

class PerDocExtractPayload(_Strict):              # what the LLM returns (no source_file)
    themes: list[str]
    insights: list[str]
    risks: list[str]
    opportunities: list[str]
    actions: list[str]
    notes: str | None                            # required field, may be null

class PerDocExtract(_Strict):                     # what the pipeline emits (source_file pinned)
    source_file: str
    # ... same fields as the payload

class AggregatedFindings(_Strict):
    themes: list[Theme]
    insights: list[Insight]
    risks: list[Risk]
    opportunities: list[Opportunity]
    actions: list[Action]

class SummaryReport(_Strict):
    executive_summary: str
    findings: AggregatedFindings
    assumptions: list[str]
    limitations: list[str]
    metadata: ReportMetadata        # docs_processed, docs_failed, tokens, cost, model, timing
```

The wire/domain split (`PerDocExtractPayload` vs `PerDocExtract`) exists because OpenAI's strict structured-output mode requires every field in the schema to be required (no defaults), but we want to attach the source filename ourselves rather than ask the model to provide it. The same split logic applies to keeping ReportMetadata's run-stats out of the LLM-facing `AggregatedFindings`.

## CLI surface

```bash
python -m src.cli \
  --input_dir ./input_docs \
  --output ./summary_report.md \
  --model openai/gpt-4o-mini \
  --concurrency 5 \
  --format both \
  --mock                              # bypass API entirely
```

(Both `--input_dir` underscore form and `--input-dir` hyphen form are accepted, matching the brief and conventional Python respectively.)

The eval suite is its own module:

```bash
python -m eval --report path/to/summary_report.json
python -m eval --report path/to/summary_report.json --strict
```

Or via Make: `make run-mock`, `make run`, `make eval-good`, `make eval-bad`. See `Makefile` and `README.md` for the full set.

## Outputs

**`summary_report.md`** — executive-readable. Sections per the brief: executive summary, themes, insights, risks, opportunities, recommended actions, assumptions, limitations. Each theme/insight carries inline citations (`note_014.txt`, `note_032.txt`).

**`summary_report.json`** — full structured output including token counts, per-stage cost breakdown, model used, run timestamp, eval-friendly machine-readable shape.

## What we deliberately do NOT include

- **No vector DB / embeddings / RAG.** The task is summarisation, not retrieval. Adding embeddings is scope creep that signals can't-scope.
- **No frontend.** CLI is the right interface for this tool. A web UI would be a different project.
- **No orchestration framework.** ~50 lines of explicit async Python beats LangChain's abstractions.
- **No fine-tuning, no agents, no multi-step reasoning loops.** Each stage is one structured LLM call. Predictable, debuggable, cheap.
- **No multi-tenant, no user accounts, no persistence layer.** Out of scope for a CLI tool.

## Trade-offs we accept

- **Per-doc extraction loses cross-doc context.** Mitigated by the reduce stage operating over compact structured extracts. A document that only makes sense relative to another doc will lose nuance — acceptable for this task domain.
- **Theme clustering happens in the reduce LLM call**, not in deterministic code. Less reproducible than a `sklearn` clusterer would be, but produces semantically meaningful theme labels for free. Production might add embedding-based clustering as a pre-step.
- **The synthesis stage is the only place free-form prose is generated.** All structure comes from earlier stages. Limits creative narrative but makes the report consistent and gradeable.

## Production-readiness notes

What this architecture is missing for production deployment, documented honestly in the README:

- Real response cache (Redis) with TTLs and invalidation
- Structured logging (JSON to stdout, parseable by Cloud Logging / Datadog)
- Metrics export (Prometheus or OpenTelemetry)
- Rate limiting respecting upstream provider quotas
- Per-tenant isolation if multi-customer
- PII detection / redaction at ingest
- Schema versioning and migration story
- Human-in-loop review before reports go to stakeholders
- Evaluation in production (sampled spot-checks, drift monitoring)
