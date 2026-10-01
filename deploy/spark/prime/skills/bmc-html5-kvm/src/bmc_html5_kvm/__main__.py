"""Run the isolated HTML5 console worker, never a public HTTP server."""

import sys

from . import server_main, worker_main


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        if len(sys.argv) != 3 or sys.argv[1] != "--server":
            raise SystemExit("Use --server only inside the dedicated OpenShell sandbox")
        raise SystemExit(server_main(sys.argv[2]))
    raise SystemExit(worker_main())
