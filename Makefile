.PHONY: help install install-dev test test-all lint format typecheck eval eval-good eval-bad run run-mock clean

PY ?= .venv/bin/python
PIP ?= .venv/bin/pip
INPUT_DIR ?= input_docs
OUTPUT ?= summary_report.md
MODEL ?= openai/gpt-4o-mini

help:
	@echo "Targets:"
	@echo "  install        install runtime deps (pip install -e .)"
	@echo "  install-dev    install runtime + dev deps (pytest, ruff, mypy)"
	@echo "  test           run unit + integration tests (mock provider, no API key needed)"
	@echo "  test-all       run all tests including @pytest.mark.expensive (requires OPENROUTER_API_KEY)"
	@echo "  lint           ruff lint check"
	@echo "  format         ruff format"
	@echo "  typecheck      mypy --strict"
	@echo "  eval           run eval against both fake fixtures"
	@echo "  eval-good      eval the fake-good fixture (should PASS)"
	@echo "  eval-bad       eval the fake-bad fixture (should FAIL)"
	@echo "  run-mock       analyse input_docs/ with the mock provider (no API key)"
	@echo "  run            analyse input_docs/ via OpenRouter (needs OPENROUTER_API_KEY)"

install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e ".[dev]"

test:
	$(PY) -m pytest

test-all:
	$(PY) -m pytest -m "expensive or not expensive"

lint:
	$(PY) -m ruff check src eval tests

format:
	$(PY) -m ruff format src eval tests

typecheck:
	$(PY) -m mypy

eval-good:
	$(PY) -m eval --report eval/fixtures/fake_good.json

eval-bad:
	$(PY) -m eval --report eval/fixtures/fake_bad.json

eval: eval-good eval-bad

run-mock:
	$(PY) -m src.cli --input_dir $(INPUT_DIR) --output $(OUTPUT) --mock

run:
	$(PY) -m src.cli --input_dir $(INPUT_DIR) --output $(OUTPUT) --model $(MODEL)

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
