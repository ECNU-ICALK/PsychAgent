"""Module entrypoint for ``python -m rft`` and ``python -m src.rft``."""

from __future__ import annotations

from .main import main


if __name__ == "__main__":
    raise SystemExit(main())
