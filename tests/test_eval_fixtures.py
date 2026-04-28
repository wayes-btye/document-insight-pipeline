"""Sanity tests: fake_good passes the eval; fake_bad fails in known ways.

These tests are the proof that the eval distinguishes good output from bad
BEFORE the real tool is built. If a tool produces something close to fake_good,
it should pass; if it produces something like fake_bad, it should fail at
specific named metrics.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.grader import (
    discover_valid_filenames,
    grade,
    load_manifest,
    load_thresholds,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def manifest():
    return load_manifest(REPO_ROOT / "eval" / "manifest.yaml")


@pytest.fixture(scope="module")
def thresholds():
    return load_thresholds(REPO_ROOT / "eval" / "thresholds.yaml")


@pytest.fixture(scope="module")
def valid_filenames():
    return discover_valid_filenames(REPO_ROOT / "input_docs")


def _load(path: Path):
    with path.open() as f:
        return json.load(f)


def _metric(tier, name):
    for m in tier.metrics:
        if m.name == name:
            return m
    raise AssertionError(f"metric {name} not found in tier {tier.tier}")


def test_fake_good_passes_all_tiers(manifest, thresholds, valid_filenames):
    raw = _load(REPO_ROOT / "eval" / "fixtures" / "fake_good.json")
    tiers, parsed = grade(raw, manifest, thresholds, valid_filenames)
    assert parsed is not None, "fake_good must parse against the schema"
    failures = [(t.tier, m.name, m.value, m.threshold) for t in tiers for m in t.metrics if not m.passed]
    assert not failures, f"fake_good should pass every metric, got failures: {failures}"


def test_fake_bad_parses_but_fails_known_metrics(manifest, thresholds, valid_filenames):
    raw = _load(REPO_ROOT / "eval" / "fixtures" / "fake_bad.json")
    tiers, parsed = grade(raw, manifest, thresholds, valid_filenames)
    assert parsed is not None, "fake_bad is schema-valid by design (failures are about content)"

    tier1, tier2 = tiers[0], tiers[1]

    halluc = _metric(tier1, "citation_hallucination_rate")
    assert not halluc.passed, "fake_bad cites note_999.txt; hallucination metric must fail"
    assert "note_999.txt" in halluc.details

    primary_recall = _metric(tier2, "high_theme_recall")
    assert not primary_recall.passed, (
        "fake_bad surfaces only one primary theme (pricing_pressure); "
        "recall must fall below the 0.85 threshold"
    )

    fp = _metric(tier2, "false_positive_rate_on_distractors")
    assert not fp.passed, "fake_bad surfaces office_relocation and dismissed_consumer_pivot; FP must fail"
    assert "Office relocation" in fp.details, (
        f"expected office relocation theme in FP details, got: {fp.details}"
    )
    assert "Consumer market expansion" in fp.details, (
        f"expected consumer-pivot theme in FP details, got: {fp.details}"
    )
