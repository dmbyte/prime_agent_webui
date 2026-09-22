"""Private entry point for the isolated browser worker."""

import sys

from . import _worker_main


if __name__ == "__main__" and "--worker" in sys.argv:
    raise SystemExit(_worker_main())
