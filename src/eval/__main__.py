"""Module entrypoint for ``python -m eval`` and ``python -m src.eval``."""

from __future__ import annotations

from .main import main


if __name__ == "__main__":
    raise SystemExit(main())
