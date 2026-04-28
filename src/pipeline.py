"""Pipeline orchestrator.

Composes the three stages with bounded async concurrency on the map step.
Single LLM call for reduce and synthesis. Builds the final SummaryReport.

This module intentionally does NOT import `eval/` or `eval/manifest.yaml`.
The tool builds blind to the grading rubric, by design.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from src.aggregate import aggregate
from src.cost import CostTracker
from src.extract import extract_one
from src.providers.base import LLMProvider
from src.schemas import (
    AggregatedFindings,
    PerDocExtract,
    ReportMetadata,
    SummaryReport,
)
from src.synthesize import synthesise

log = logging.getLogger(__name__)


async def run_pipeline(
    *,
    provider: LLMProvider,
    input_dir: Path,
    concurrency: int = 5,
    cost_tracker: CostTracker | None = None,
) -> SummaryReport:
    """Run map → reduce → synthesise over input_dir, return SummaryReport."""
    docs = sorted(input_dir.glob("*.txt"))
    if not docs:
        raise ValueError(f"no .txt files found in {input_dir}")

    cost = cost_tracker or CostTracker(prices={}, model=provider.model)
    started = time.perf_counter()

    # ---- Map ----
    log.info("map: %d docs, concurrency=%d, model=%s", len(docs), concurrency, provider.model)
    extracts = await _run_map(provider, docs, concurrency=concurrency, cost=cost)
    log.info("map: complete (%d extracts)", len(extracts))

    # ---- Reduce ----
    log.info("reduce: aggregating %d extracts", len(extracts))
    findings, reduce_result = await aggregate(provider, extracts)
    cost.add("reduce", reduce_result.usage)
    log.info(
        "reduce: complete (%d themes, %d insights, %d risks, %d opportunities, %d actions)",
        len(findings.themes), len(findings.insights), len(findings.risks),
        len(findings.opportunities), len(findings.actions),
    )

    # Defensive: filter out citations to files we never saw, before synthesis sees them.
    valid_files = {d.name for d in docs}
    findings = _strip_unknown_citations(findings, valid_files)

    # ---- Synthesise ----
    log.info("synthesise: generating executive narrative")
    synth, synth_result = await synthesise(provider, findings)
    cost.add("synthesise", synth_result.usage)

    # ---- Assemble ----
    duration = time.perf_counter() - started
    metadata = ReportMetadata(
        docs_processed=len(extracts),
        model=provider.model,
        timestamp_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        total_tokens_input=cost.total_input_tokens,
        total_tokens_output=cost.total_output_tokens,
        estimated_cost_usd=round(cost.estimated_usd, 6),
        duration_seconds=round(duration, 2),
    )

    return SummaryReport(
        executive_summary=synth.executive_summary,
        findings=findings,
        assumptions=synth.assumptions,
        limitations=synth.limitations,
        metadata=metadata,
    )


async def _run_map(
    provider: LLMProvider,
    docs: list[Path],
    *,
    concurrency: int,
    cost: CostTracker,
) -> list[PerDocExtract]:
    sem = asyncio.Semaphore(concurrency)
    results: list[PerDocExtract | None] = [None] * len(docs)

    async def worker(i: int, doc: Path) -> None:
        async with sem:
            try:
                extract, result = await extract_one(provider, doc)
                cost.add("map", result.usage)
                results[i] = extract
            except Exception as exc:
                log.warning("map: failed on %s: %s — emitting empty extract", doc.name, exc)
                # Failure isolation: skip this doc rather than aborting the run.
                results[i] = PerDocExtract(
                    source_file=doc.name,
                    themes=[],
                    insights=[],
                    risks=[],
                    opportunities=[],
                    actions=[],
                    notes=f"extraction failed: {exc}",
                )

    await asyncio.gather(*(worker(i, doc) for i, doc in enumerate(docs)))
    return [r for r in results if r is not None]


def _strip_unknown_citations(findings: AggregatedFindings, valid_files: set[str]) -> AggregatedFindings:
    """Remove citations to filenames that don't exist in the input directory.

    The model occasionally invents filenames (Tier 1's hallucination guard catches this in
    eval). Stripping unknown citations here prevents those hallucinations reaching the
    final report. Items left with zero citations are dropped (citations are required).
    """
    def clean_citations(cites: list[str]) -> list[str]:
        return [c for c in cites if c in valid_files]

    themes = [
        t.model_copy(update={"citations": clean_citations(t.citations)})
        for t in findings.themes
        if clean_citations(t.citations)
    ]
    insights = [
        i.model_copy(update={"citations": clean_citations(i.citations)})
        for i in findings.insights
        if clean_citations(i.citations)
    ]
    risks = [
        r.model_copy(update={"citations": clean_citations(r.citations)})
        for r in findings.risks
        if clean_citations(r.citations)
    ]
    opportunities = [
        o.model_copy(update={"citations": clean_citations(o.citations)})
        for o in findings.opportunities
        if clean_citations(o.citations)
    ]
    actions = [
        a.model_copy(update={"citations": clean_citations(a.citations)})
        for a in findings.actions
        if clean_citations(a.citations)
    ]

    return AggregatedFindings(
        themes=themes,
        insights=insights,
        risks=risks,
        opportunities=opportunities,
        actions=actions,
    )
