# Top-level decisions and trade-offs

A reviewer's quick reference. What we chose, what we considered, and why. Honest about the costs of the path we took.

The map-reduce architecture is the most consequential decision and gets the longest treatment. The rest is a table.

---

## The big one: how to process 100 documents

We make **one LLM call per document, then aggregate the structured extracts**. We do not put all the documents into one prompt. We do not retrieve relevant chunks via embeddings. We do not let the model decide which files to read.

### Approaches considered

| Approach | What it is | Verdict |
|---|---|---|
| **Map-reduce (chosen)** | One LLM call per doc → one call to aggregate → one call to synthesise narrative | ✅ Chosen |
| Single-shot context stuffing | All 100 docs concatenated into one giant prompt; the model produces the whole report in one call | ❌ Rejected |
| RAG (retrieval-augmented generation) | Chunk + embed all docs, query a vector store with synthesised queries, summarise top-k | ❌ Wrong task |
| Hybrid retrieval + summarise top-k | RAG to surface relevant chunks, summarise just those | ❌ Wrong task |
| Agentic file search | Give the model tools (grep, read), let it explore and decide what to read (the way Claude Code itself navigates a codebase) | ❌ Wrong fit |

### Why map-reduce won

1. **Citations stay accurate.** During the map stage the model sees exactly one document. It physically cannot hallucinate which file a finding came from, because no other file is in scope. The pipeline pins the source filename outside the model's reach.
2. **Cost is predictable.** Each map call is small and bounded. We know upfront roughly what 100 docs will cost (~$0.025 against `gpt-4o-mini`). Single-shot would vary wildly with corpus size.
3. **It scales linearly.** Architecture works the same for 1,000 or 10,000 docs. Single-shot breaks at the context window. RAG would scale, but it's solving a different problem (see below).
4. **Per-doc failures don't kill the run.** If 3 of 100 docs fail extraction (timeout, refusal, malformed), the pipeline emits empty extracts for those, the run continues, and the report flags the gap. Single-shot fails atomically.
5. **It's observable.** Per-doc structured outputs are inspectable, diff-able, and testable in isolation. A 100-doc mega-prompt is a black box where you can't tell which doc influenced which finding.
6. **It caches naturally.** Re-running the reduce/synthesis stage during prompt iteration doesn't re-bill the per-doc map calls. With single-shot, every iteration re-bills the full prompt.

### Honest drawbacks of map-reduce

We accept these. Mitigations are in the architecture.

| Drawback | Why it matters | Mitigation |
|---|---|---|
| **More LLM calls** (101 + 1 + 1 = 103 vs 1) | Longer wall-clock time; more network round-trips; more places for transient failure | Bounded async (Semaphore=5) for the map stage. Tenacity retries on schema failures. SDK retries on 429/5xx. |
| **Cross-doc context is lost in the map stage** | A document that only makes sense relative to another (e.g. "as discussed in note_003") will lose that nuance during extraction | The reduce stage operates over the structured extracts of all docs together, so cross-doc clustering happens there. We accept losing some subtlety in exchange for citation accuracy. |
| **Theme quality depends on the reduce-stage prompt** | All theme clustering happens in one LLM call. If the reduce model is weak, themes will be noisy, vague, or duplicated | Defended in the reduce prompt (cluster aggressively, merge paraphrases). Production: use a stronger model for reduce. The Tier 3 findings document the gap with `gpt-4o-mini`. |
| **More code to maintain** | Three modules (extract, aggregate, synthesise) plus the orchestrator vs one prompt + one parse | The code is ~50 lines of explicit Python per stage. Not heavy. The trade-off is well worth it for the auditability. |
| **Per-doc structured-output overhead** | Every map call pays for schema-to-JSON serialisation in the prompt | Schemas are small (~15 fields). Overhead is in the noise compared to document content. |

### Why not single-shot context stuffing

Modern context windows can technically hold 100 short documents. We don't do this because:

- **Lost-in-the-middle is well-documented.** Models attend less reliably to content in the middle of long contexts. A theme that recurs in docs 40-60 is more likely to be missed.
- **Citation hallucination scales with context length.** Asked "which docs support theme X?" against 100 in-prompt docs, models will confidently cite filenames that don't appear, or cite a doc that doesn't actually discuss X. Per-doc extraction makes this physically impossible.
- **Atomic failure.** If anything goes wrong (timeout, refusal, malformed JSON), you re-run the entire 100-doc prompt. Map-reduce only re-runs the failed map call.
- **No incremental cost control.** You can't cache. You can't skip docs you've already processed. Re-running for a prompt tweak burns the full token cost again.

We'd consider single-shot for a *small homogeneous* corpus (10-20 docs of similar shape) where citation precision wasn't critical. Not this task.

### Why not RAG

RAG is for **retrieval and question-answering**, not summarisation. The user has a question; RAG finds relevant chunks; the model answers from them. That's not what the brief asks for.

The brief asks: *give me a summary of the whole corpus*. There's no query. There are no top-k relevant docs because every doc is potentially relevant. RAG would systematically miss long-tail themes by definition (anything outside the top-k of the synthesised query).

It would also add: a vector DB dependency, an embedding model dependency, chunking strategy decisions, retrieval-tuning tuning loops, drift monitoring. Scope creep that buys nothing for this task.

If the use case were "ask questions over the corpus" instead of "summarise the corpus", RAG would be the right call. It isn't this use case.

### Why not agentic file search

The way Claude Code itself works: give the model `grep`, `read`, `ls`, let it explore and decide what files matter. Pros: it can find unexpected patterns and take shortcuts. Cons:

- **Non-deterministic coverage.** No guarantee the model reads every doc. It might decide to summarise based on a sample. For a portfolio review where stakeholders need confidence the whole set was considered, that's a failure mode.
- **Cost is unbounded.** Multi-turn agentic loops can rack up dozens of tool calls before producing an answer. You can't budget upfront.
- **Hard to evaluate.** The eval depends on what files the model decided to read, which varies per run. Reproducibility goes out the window.
- **Opaque reasoning.** A reviewer asking "why was theme X surfaced?" gets a transcript of the model's exploration, not a clean per-doc audit trail.

Agentic search is the right design when the corpus is *too big* to read end-to-end and the user has a specific question. Neither applies here.

### When map-reduce would be the wrong choice

Honest caveat: map-reduce isn't always right. If the corpus were 10,000 docs, the per-doc cost would dominate and you'd want a hybrid (cluster + summarise representatives). If the user had a specific question, RAG would beat both. We chose map-reduce because the brief's profile (100 docs, summary-of-everything, citations required) hits its sweet spot.

---

## All other decisions

| Decision | Chosen | Rejected | Reason |
|---|---|---|---|
| **LLM provider abstraction** | OpenAI SDK pointed at OpenRouter base URL | Native OpenAI SDK only; LangChain; LlamaIndex; direct httpx; native Anthropic SDK | Vendor-agnostic at the model layer (OpenRouter exposes 100+ models behind one API), production-grade async client, structured outputs as first-class, no orchestration-framework debt |
| **Orchestration framework** | None — direct ~50 lines of Python | LangChain; LlamaIndex; Haystack; LangGraph | We can read every line. No version churn, no abstraction debt, no breaking-change roulette. Frameworks earn their keep on multi-step agentic flows; this is three discrete LLM calls. |
| **Schema layer** | Pydantic + `client.chat.completions.parse(response_format=Model)` | Free-text + regex; raw JSON Schema; dataclasses | Schema enforces shape at the API boundary (model can't return wrong types). Single source of truth used by both pipeline and eval. |
| **Mock provider** | First-class implementation (every code path runs against it) | No mock (API for everything); pytest-mock at test time only | Eval suite runs in CI without API keys. Whole CLI runs keyless. Tests exercise real code paths, not mocked seams. |
| **Eval framework** | Three-tier (hard constraints / synthetic capability / discovered failures) | Pure eval-driven development; pure post-hoc judgement; single-tier strict | Pre-committing thresholds for things you don't know how to evaluate creates false confidence (Hamel Husain's pushback). Three tiers separate what we can pre-commit (Tier 1, 2) from what we discover (Tier 3). |
| **Sealed corpus manifest** | Manifest + tool import-isolated from manifest | Tool reads manifest as ground truth; no manifest, judge by hand | If the extraction code knows the answer key, the eval numbers mean nothing. Procedural separation is what makes the grading credible. |
| **Synthetic corpus** | Generated 101 fictional docs with planted themes + distractors | Public corpus (Enron, etc.); real anonymised data; no committed corpus | Real data: PII risk, copyright risk, no ground truth. Public corpora: wrong shape (Enron is email, not B2B advisory). Synthetic with a sealed manifest gives us controlled difficulty mechanics and known correct answers. |
| **Citation requirement** | Required field in schema (`min_length=1`) on every theme/insight/risk/opportunity/action | Optional citations; informal "see also" in prose | Forces grounding at the API boundary. The model cannot emit an ungrounded finding even if it tried — Pydantic rejects it. |
| **Citation hallucination guard** | Pipeline strips citations to filenames not in `input_docs/` before they reach output, AND eval grades hallucination rate | Trust the model; eval-only check; reject whole report on hallucination | Belt and braces. Eval catches it for grading; pipeline strips it so the report is clean even if eval isn't run. |
| **Concurrency model** | Bounded async with Semaphore=5 (configurable) | Synchronous (slow); unbounded async (rate-limited); thread pool | Async is right for I/O-bound LLM calls. Bounded prevents accidental DoS of the upstream API. 5 is a reasonable default. |
| **Retry strategy** | SDK retries (429/5xx, transient) + tenacity (schema validation failures) | SDK retries only; custom retry loop; no retries | Two failure modes need different handling. SDK is correct for transport errors. Tenacity wraps the schema-validation path because that's a model-side issue (model returned valid JSON but it doesn't match the schema). |
| **Cache** | Content-hash cache (`sha256(model + system + user + schema)`) on disk, disabled by default | No cache; in-memory cache; redis | Disk cache is enough for dev iteration on the reduce/synthesis prompts (don't re-bill the per-doc map). Disabled by default because production wants Redis with TTL. |
| **Output format** | Both Markdown (executive readable) and JSON (machine readable, eval-input-shaped) | Markdown only; JSON only | Brief allows either; we do both because they serve different consumers. JSON is what the eval grades. |
| **CLI argument style** | Both `--input_dir` and `--input-dir` accepted | Underscores only; hyphens only | Brief uses underscores in its example; conventional Python uses hyphens. Supporting both costs nothing and avoids a friction point. |
| **Frontend / Web UI** | None | React app; FastAPI + UI; Streamlit | Brief is for a CLI tool. Adding a UI is a different project. |
| **Database / persistence layer** | None | SQLite for runs; Postgres | This is a one-shot CLI invocation. No multi-user, no history. Adding a DB is scope creep. |
| **Token tokeniser** | Use the SDK's reported `usage.prompt_tokens` / `usage.completion_tokens` | Compute via tiktoken | The SDK already returns the canonical count. Re-counting locally would invite drift. |
| **Cost price table** | Static dict in `config.yaml` | Live API call to provider's pricing endpoint; hardcoded constant | Provider pricing changes occasionally; config makes it easy to update. Hardcoded would rot. Live API call would add a network dependency for a cosmetic feature. |
| **Reproducibility script for corpus** | Not implemented (canonical corpus committed) | Generate-from-scratch script | The corpus is committed. A regeneration script would just be a reference impl. Documented in `ai-assistance.md` how it was generated. Production would automate this. |
| **Docker base image** | `python:3.12-slim` two-stage build, non-root user | `python:3.12` (full); `python:3.12-alpine`; distroless | Slim balances size vs build complexity. Alpine has musl-libc compatibility issues with some Python packages. Distroless adds operational friction. Two-stage build keeps the runtime image lean. |
| **Test runner** | pytest + pytest-asyncio | unittest; trial; nose | pytest is the de facto standard. Asyncio plugin needed for async test functions. |
| **Lint + format + typecheck** | ruff (lint + format), mypy --strict | flake8 + black + isort + pylint; pyright; no typecheck | Ruff replaces 4 tools with one fast Rust binary. Mypy strict is the highest-confidence option for a small typed codebase. Pyright would also work; mypy chosen for ubiquity. |
| **Python version floor** | 3.11+ | 3.10+; 3.12+ only | 3.11 has the union-type syntax we use (`X | None`) and `asyncio.TaskGroup`. 3.12-only would be needlessly exclusive. |
| **Async runtime** | `asyncio` standard library | `trio`; `anyio` everywhere | OpenAI's `AsyncOpenAI` uses `asyncio`. Adding `trio` would mean an `anyio` adapter and confusion. |
| **Synthesis-stage prose discipline** | Hard rules in the prompt: no platitudes, no bullets in summary, concrete language only | Trust the model | Without explicit constraints, LLM exec summaries default to "strategic positioning, evolving landscape, comprehensive approach". The constraints are cheap and effective. |
| **Negation / dismissed-idea handling** | Hard rule in both map and reduce prompts: dismissed ideas are NOT opportunities | None | A document saying "we are NOT pivoting to consumer" describes a closed question, not an opportunity. Without explicit prompt rules, models surface this as opportunity. The corpus has a `dismissed_consumer_pivot` distractor specifically to test this. |

---

## Decisions explicitly deferred to "production"

These would be needed before deploying internally. Out of scope for this exercise; listed in the README's "What I'd change for production" section.

- Real response cache (Redis with TTL + invalidation)
- Structured JSON logging to stdout
- Metrics export (OpenTelemetry)
- Rate limiting that respects upstream provider quotas
- PII detection / redaction at ingest
- Schema versioning for structured outputs
- Human-in-the-loop review before reports go to stakeholders
- Eval in production: sampled spot-checks, drift monitoring
- Embedding-based theme matching in the eval (replacing substring)
- Per-tenant isolation if multi-customer
- Larger model for the reduce stage (closes Tier 2 gaps)
- Consensus across N runs (closes consistency Jaccard gap)

The point of listing them is to show we know they're missing, not to claim they're done.
