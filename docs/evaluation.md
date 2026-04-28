# Evaluation

## Philosophy

We take a deliberately blended position on LLM evaluation, informed by the current practitioner discourse:

- **Hamel Husain** [argues against pure eval-driven development](https://hamel.dev/blog/posts/evals-faq/should-i-practice-eval-driven-development.html): *"Eval-driven development sounds appealing but creates more problems than it solves. You can't anticipate what will break. Write evaluators for errors you discover, not errors you imagine."* He allows a narrow exception: *"Eval-driven development may work for specific constraints where you know exactly what success looks like."*
- **Synthetic eval corpora** are [empirically known to underestimate task difficulty](https://arxiv.org/html/2508.11758) because surface overlap between corpus and reference makes matching too easy.
- **Pure post-hoc evaluation**, on the other hand, lets the developer (or AI assistant) calibrate "what good looks like" to whatever the system happens to produce — a subtle but real form of cheating.

Our response is a three-tier framework. Each tier has a different commitment time and a different role.

## The three tiers

### Tier 1 — Hard constraints, pre-committed

These are unambiguous "we know exactly what success looks like" metrics — the legitimate eval-first cases per Hamel. Pre-writing them is defensible because the failure mode is well-defined and binary.

| Metric | Threshold | Why pre-commit is justified |
|--------|-----------|------------------------------|
| **Schema validity** | 100% | The Pydantic schema is the contract. A non-validating output is broken, full stop. |
| **Citation hallucination rate** | 0% | Every cited filename must exist in `input_docs/`. Zero tolerance — citing a non-existent file is the worst possible failure for a tool whose value is grounding. |
| **Required fields populated** | 100% | Every theme has ≥1 citation, every section is non-empty. Empty fields signal pipeline failure or model laziness, not creativity. |
| **Report section completeness** | 100% | All eight sections from the brief (exec summary, themes, insights, risks, opportunities, actions, assumptions, limitations) are present. |

Tier 1 is strict and runs on every output before any other metric. A failure here aborts the eval — there's no point measuring recall on a malformed output.

### Tier 2 — Capability on synthetic distribution, pre-committed but qualified

Measured against the sealed `eval/manifest.yaml`. These metrics are pre-committed but explicitly framed as **indicative**, not production-grade. Numbers here measure the tool's behaviour on our synthetic distribution; they do not generalise to arbitrary corpora.

| Metric | Threshold | What it measures |
|--------|-----------|------------------|
| **Primary theme recall** | ≥0.85 | Of high-salience planted themes, fraction surfaced (matched by canonical name + aliases, then verified by reading the description). |
| **Secondary theme recall** | ≥0.70 | Same, for medium-salience themes. |
| **Minor theme recall** | ≥0.50 | Lower bar — minor themes are a stretch goal, not a must-find. |
| **Citation precision** | ≥0.90 | For each cited (theme, doc) pair, does the cited doc actually contain that theme? Verified by re-reading the doc against the theme description. |
| **Document coverage** | ≥0.75 | Fraction of input documents cited at least once across all themes. Distractor-only docs excluded from denominator. |
| **False positive rate on distractors** | ≤0.10 | Maximum fraction of distractor themes (`office_relocation`, `dismissed_consumer_pivot`) surfaced as report items. |
| **Run-to-run consistency (Jaccard)** | ≥0.65 | Theme set overlap when the same input is processed twice. Below this and the tool is too non-deterministic to trust. |

Tier 2 thresholds are achievable but not trivial. They were set based on what a reasonable map-reduce pipeline with structured outputs should hit, not retrofitted to whatever this particular implementation produces.

### Tier 3 — Discovered failure modes, post-hoc

This is where Hamel's principle directly applies. After the first real run, we perform error analysis on the actual outputs and document specific failure modes that occurred. Tier 3 evals are then written for those discovered failures.

Examples of what *might* land here (we won't know until we run):
- Theme conflation (two distinct themes merged into one)
- Over-decomposition (one theme split into two redundant ones)
- Generic platitude actions ("monitor the situation", "engage stakeholders")
- Specific phrasing patterns that read as LLM-generated
- Failure modes specific to certain document types

Tier 3 is documented in `eval/results/tier3_findings.md` after Phase 6 of the build. It's the most valuable tier — it measures what's actually broken — but cannot be written before the system exists.

## Why this beats pure eval-first

Pure EDD on a system like this would commit us to evaluating imagined failure modes, many of which never occur, while missing the ones that do. Pure post-hoc evaluation opens the door to grading-on-the-curve. The blended framework:

- Pre-commits the failures that are universal and well-understood (Tiers 1 + 2)
- Defers the evaluation of system-specific behaviour to after the system exists (Tier 3)
- Names this trade-off explicitly so anyone reading the eval results understands what they mean

## Defence of the synthetic test set

Anticipated objection: *"You wrote the corpus and the eval. Of course it passes."* Honest defence:

1. **The corpus contains deliberate difficulty mechanics** (see `corpus-design.md` § Deliberate difficulty mechanics): theme overlap, implicit themes, negation, variable salience, distractor noise, near-duplicates, stylistic variety. The corpus is not a soft target.
2. **Citation precision is grounded in raw text.** A citation passes only if the cited doc actually contains the theme. The grader re-reads the document; the theme label cannot be self-validating.
3. **Procedural separation.** The extraction pipeline (`src/extract.py`, `src/aggregate.py`, `src/synthesize.py`) does not import the manifest. The eval harness (`tests/eval/`) does. The tool is structurally blind to its own grading rubric.
4. **Distractor and false-positive tests.** Tier 2 includes a false-positive rate on distractors. The corpus contains intentional traps (`dismissed_consumer_pivot`); a tool that scores well on recall while also surfacing dismissed pivots fails the eval.
5. **Honest framing.** The README explicitly states that Tier 2 numbers are indicative on a synthetic distribution. They are evidence the methodology works, not a claim of production-readiness.

## What production-grade evaluation would look like

Beyond what this project ships:

- **Real held-out evaluation set** — actual business documents from the deployment domain, themes annotated by domain experts, refreshed quarterly to avoid overfitting.
- **LLM-as-judge for subjective dimensions** — executive readability, action specificity, tonal appropriateness. Validated against human ratings on a sample.
- **Pairwise preference evaluation** — A/B prompts, model versions, or pipeline configs against held-out tasks. More signal than absolute scores.
- **Production drift monitoring** — sampled spot-checks of live outputs; trigger re-evaluation if drift exceeds threshold.
- **Per-segment evaluation** — break down metrics by document type, length bucket, language, domain. Aggregate scores hide failure pockets.
- **Cost / latency joint optimisation** — eval not just for quality but for the quality-cost-latency Pareto.
- **Human-in-loop calibration** — periodic SME review of edge cases, feeding back into prompt and threshold tuning.

These are out of scope here. They are listed in the README as "what would change for production" — substantive answers, not handwaving.

## How the eval suite runs

```bash
make eval                              # all tiers against last committed sample output
python -m src.cli eval --output ./summary_report.json   # against arbitrary output
python -m src.cli eval --tier 1        # constraint checks only — fast
python -m src.cli eval --tier 2        # capability checks against manifest
```

Outputs land in `eval/results/<timestamp>/` with:
- `tier1.json` — pass/fail per constraint
- `tier2.json` — per-metric scores + per-theme recall breakdown
- `tier3.md` — written manually after error analysis
- `summary.md` — human-readable aggregation

`eval/results/` contains committed reference runs from the canonical `examples/sample_summary_report.json`. These are the numbers cited in the README.

## References

- Hamel Husain — [Should I practice eval-driven development?](https://hamel.dev/blog/posts/evals-faq/should-i-practice-eval-driven-development.html)
- Hamel Husain — [Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/)
- Eugene Yan — [An LLM-as-Judge Won't Save the Product — Fixing Your Process Will](https://eugeneyan.com/writing/eval-process/)
- *Can we Evaluate RAGs with Synthetic Data?* — [arXiv 2508.11758](https://arxiv.org/html/2508.11758)
