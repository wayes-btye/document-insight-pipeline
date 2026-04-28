# Document Insight Pipeline

Repo-level guidance for Claude Code sessions working on this project.

## Parent context

Load `~/CLAUDE.md` for top-level instructions — Claudette identity, communication style, sync rules, scheduled tasks, skill placement, browser automation, and the rest of the broader infrastructure.

## What this project is

A small Python application that takes a folder of text documents, uses an LLM to analyse them, and produces a business-friendly summary report (executive summary, themes, insights, risks, opportunities, recommended actions, assumptions, limitations).

CLI tool. Map-reduce architecture. OpenAI SDK pointed at OpenRouter for model flexibility. Mock provider as a first-class option (lets the tool run with no API key).

## Project state — start here every session

**Current state and next steps live in [`docs/build-plan.md`](docs/build-plan.md).** Read it first to know where the project is in its build sequence.

**AI usage is documented in [`docs/ai-assistance.md`](docs/ai-assistance.md).** Update it when meaningfully new tools or workflows are used.

## Key references

| File | Purpose |
|------|---------|
| `docs/architecture.md` | Map-reduce design, components, data shapes, LLM provider strategy, what we deliberately do not include |
| `docs/corpus-design.md` | Fictional scenario, doc-type taxonomy, theme planting, deliberate difficulty mechanics |
| `docs/evaluation.md` | Three-tier eval framework (hard constraints, synthetic capability, post-hoc discovered failures), defence of approach |
| `docs/build-plan.md` | Phased plan with status. Single source of truth for "where are we." |
| `docs/ai-assistance.md` | How AI was used building this. Becomes the basis for the README's AI-assistance note. |
| `eval/manifest.yaml` | Sealed corpus manifest — ground truth for Tier 2 evaluation. Populated; do not modify without re-generating corpus. |
| `eval/thresholds.yaml` | Pass thresholds for evaluation tiers. |
| `input_docs/*.txt` | 101 fictional business documents. Committed corpus. Do not regenerate without coordinating with manifest. |
| `private-context/` | Gitignored. Reference copy of the original brief. Not committed. |

## Hard rules

1. **The extraction pipeline must not import `eval/manifest.yaml`.** The eval grades against the manifest; the tool builds blind to it. This procedural separation is what makes the eval numbers mean anything. Violating this destroys the entire grading premise.
2. **No LangChain, LlamaIndex, or orchestration frameworks.** Direct OpenAI SDK + Pydantic + httpx is the entire stack. Adding a framework here is scope creep and reduces transparency.
3. **Mock provider is first-class, not a hack.** Every code path that calls the LLM must work against the mock provider. The eval suite runs in mock mode in CI without API keys.
4. **No real PII or proprietary data anywhere.** All names, companies, numbers in the corpus are fictional. The corpus is committed publicly-readable.
5. **No mention of any specific employer, recruiter, brief origin, or assessment context anywhere in committed files.** The repo reads as a portfolio / internal tool. Strategy / positioning notes (if any) live only in `private-context/` (gitignored).

## Current decisions

(Pulled forward for visibility. See `docs/build-plan.md` for full reasoning.)

- **Architecture**: map → reduce → synthesise. Per-doc structured extraction with citations pinned, then aggregation over compact extracts, then business-facing report from aggregate.
- **LLM provider**: OpenAI SDK pointed at OpenRouter. Default model `openai/gpt-4o-mini`. Mock provider for keyless runs.
- **Eval philosophy**: three tiers. Tier 1 hard constraints pre-committed (schema validity, citation hallucination = 0%). Tier 2 capability against synthetic manifest (recall, precision, coverage, false-positive rate on distractors). Tier 3 discovered failures post-hoc.
- **Corpus**: 101 docs, 5 brief categories + 5% noise. Sealed manifest in `eval/manifest.yaml`.
- **No frontend, no DB, no RAG, no Docker until Phase 7.**

## Cross-repo reference

`~/repositories/meeting-intelligence/` is available as reference. Its `CLAUDE.md` and `README.md` document architectural patterns and stack decisions for a parallel project. Treat as reference, not template — this repo is intentionally smaller in scope.

---

[🎨 Generate Infographic](http://100.127.16.116:5055/generate-doc/CLAUDE.md)
