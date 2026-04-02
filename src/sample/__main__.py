"""Module entrypoint for ``python -m sample`` and ``python -m src.sample``."""

from __future__ import annotations

from .main import main


if __name__ == "__main__":
    raise SystemExit(main())

