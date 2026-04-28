"""Command-line entry point.

```
python -m src.cli --input_dir ./input_docs --output ./summary_report.md
python -m src.cli --input-dir ./input_docs --output ./summary_report.md --mock
```

(Both underscore and hyphen forms of `--input_dir` / `--input-dir` are accepted, matching
the brief and the architecture doc respectively.)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from src.config import Config
from src.cost import CostTracker
from src.output import write_outputs
from src.pipeline import run_pipeline
from src.providers.base import LLMProvider
from src.providers.mock import MockProvider
from src.providers.openrouter import OpenRouterProvider

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="analyze_docs",
        description="Analyse a folder of .txt documents and produce a business summary report.",
    )
    p.add_argument("--input_dir", "--input-dir", dest="input_dir", type=Path, default=Path("input_docs"),
                   help="directory of .txt files to analyse (default: ./input_docs)")
    p.add_argument("--output", type=Path, default=Path("summary_report.md"),
                   help="output path. Extension is replaced with .md / .json depending on --format.")
    p.add_argument("--model", type=str, default=None,
                   help="OpenRouter model id (default: from config.yaml; e.g. openai/gpt-4o-mini)")
    p.add_argument("--batch-size", "--batch_size", dest="batch_size", type=int, default=None,
                   help="(reserved) batch size for grouping docs; the map stage parallelises per-doc, so this is informational only")
    p.add_argument("--concurrency", type=int, default=None,
                   help="bounded concurrency for the map stage (default: 5)")
    p.add_argument("--format", choices=("md", "json", "both"), default=None,
                   help="output format(s) (default: both)")
    p.add_argument("--mock", action="store_true",
                   help="use the deterministic mock provider; no API key needed")
    p.add_argument("--config", type=Path, default=REPO_ROOT / "config.yaml",
                   help="path to config.yaml (default: ./config.yaml)")
    p.add_argument("--cache", action="store_true",
                   help="enable on-disk response cache (overrides config)")
    p.add_argument("--no-cache", action="store_true",
                   help="disable on-disk response cache (overrides config)")
    p.add_argument("--quiet", action="store_true", help="suppress info logs")
    p.add_argument("--verbose", action="store_true", help="enable debug logs")
    return p


def _resolve_config(args: argparse.Namespace) -> Config:
    cfg = Config.from_file(args.config) if args.config and args.config.exists() else Config.defaults()
    if args.model:
        cfg.provider.model = args.model
    if args.concurrency is not None:
        cfg.pipeline.concurrency = args.concurrency
    if args.format:
        cfg.pipeline.format = args.format
    if args.cache:
        cfg.cache.enabled = True
    if args.no_cache:
        cfg.cache.enabled = False
    return cfg


def _build_provider(args: argparse.Namespace, cfg: Config) -> LLMProvider:
    if args.mock:
        return MockProvider(model=cfg.provider.model if args.model else "mock/keyword-heuristic-v1")
    _load_dotenv()  # best-effort
    return OpenRouterProvider(
        model=cfg.provider.model,
        base_url=cfg.provider.base_url,
        timeout_seconds=cfg.provider.timeout_seconds,
        temperature=cfg.provider.temperature,
    )


def _load_dotenv() -> None:
    """Tiny .env loader so we don't depend on python-dotenv. Best-effort.

    Handles: blank lines, full-line comments, KEY=VALUE pairs with optional
    surrounding double or single quotes, and trailing inline comments (` # ...`).
    Does NOT support: multi-line values, escape sequences inside values,
    unquoted values containing `#` characters. If you need those, install
    python-dotenv and replace this.
    """
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        # Quoted value: take everything inside the matching closing quote;
        # ignore anything after it (e.g. trailing inline comment).
        if v.startswith(('"', "'")):
            quote = v[0]
            end = v.find(quote, 1)
            if end != -1:
                v = v[1:end]
        else:
            # Unquoted value: strip a trailing inline comment introduced by ` #`
            comment_start = v.find(" #")
            if comment_start != -1:
                v = v[:comment_start].rstrip()
        if k:
            os.environ.setdefault(k, v)


async def _amain(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    level = logging.DEBUG if args.verbose else (logging.WARNING if args.quiet else logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    cfg = _resolve_config(args)
    if not args.input_dir.exists():
        print(f"error: input_dir {args.input_dir} does not exist", file=sys.stderr)
        return 2

    provider = _build_provider(args, cfg)
    cost = CostTracker(prices=cfg.cost.prices, model=cfg.provider.model)

    log.info("provider=%s model=%s mock=%s", provider.name, provider.model, args.mock)

    report = await run_pipeline(
        provider=provider,
        input_dir=args.input_dir,
        concurrency=cfg.pipeline.concurrency,
        cost_tracker=cost,
    )

    written = write_outputs(report, args.output, cfg.pipeline.format)
    for w in written:
        print(f"wrote {w}")

    print(
        f"\nDone. {report.metadata.docs_processed} docs processed in "
        f"{report.metadata.duration_seconds:.1f}s "
        f"(~${report.metadata.estimated_cost_usd:.4f}, "
        f"{report.metadata.total_tokens_input:,} + {report.metadata.total_tokens_output:,} tokens)."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv))


if __name__ == "__main__":
    sys.exit(main())
