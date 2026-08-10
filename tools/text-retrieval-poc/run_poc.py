#!/usr/bin/env python3
"""Repository-local entry point; no package installation is required."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from veritymesh_poc.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
