"""Allow running `python -m sengled_bridge`."""

import sys
from sengled_bridge.cli import main

if __name__ == "__main__":
    sys.exit(main())
