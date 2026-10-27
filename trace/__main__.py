"""Allow running Trace as a module: python -m trace"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
