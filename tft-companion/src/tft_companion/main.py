"""Console entry point (see [project.scripts] in pyproject.toml)."""
from __future__ import annotations

import sys

from .app import main as _main


def main() -> None:
    sys.exit(_main())


if __name__ == "__main__":
    main()
