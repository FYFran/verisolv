"""Allow ``python -m verisolv`` to reach the JSON command line."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
