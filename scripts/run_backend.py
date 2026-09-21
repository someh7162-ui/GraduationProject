from __future__ import annotations

import threading
import time
import sys
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parents[1]
STOP_REQUEST = ROOT / ".private" / "runtime" / "project-stop.request"
sys.path.insert(0, str(ROOT))


def main() -> None:
    server = uvicorn.Server(
        uvicorn.Config(
            "app.main:app",
            host="127.0.0.1",
            port=8000,
        )
    )

    def watch_for_stop() -> None:
        while not STOP_REQUEST.exists():
            time.sleep(0.25)
        server.should_exit = True

    threading.Thread(target=watch_for_stop, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
