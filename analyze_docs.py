#!/usr/bin/env python3
"""Top-level CLI shim matching the brief's example invocation.

The canonical entry point is `python -m src.cli`. This shim lets
`python analyze_docs.py ...` work the same way for users who unzipped the repo.
"""

from __future__ import annotations

import sys

from src.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
