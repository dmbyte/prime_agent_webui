"""Private entry points for the browser broker and isolated worker."""

import sys

from . import _daemon_main, _worker_main


if __name__ == "__main__":
    if "--worker" in sys.argv:
        raise SystemExit(_worker_main())
    if "--daemon" in sys.argv:
        index = sys.argv.index("--daemon")
        socket_path = sys.argv[index + 1] if len(sys.argv) > index + 1 else "/tmp/prime-bmc-browser.sock"
        raise SystemExit(_daemon_main(socket_path))
