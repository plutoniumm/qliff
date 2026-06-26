from __future__ import annotations

import argparse
import threading
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="qliff-server", description="launch qliff studio"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8731)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "qliff studio needs the [studio] extra:\n  pip install 'qliff[studio]'"
        )

    url = f"http://{args.host}:{args.port}"
    browser_timer = None
    if not args.no_browser:
        # open once the server is likely up; harmless if it races slightly. A daemon
        # timer so a Ctrl-C in the first second can never delay exit or pop a browser
        # open after you've already quit -- it's also cancelled in the finally below.
        browser_timer = threading.Timer(1.0, lambda: webbrowser.open(url))
        browser_timer.daemon = True
        browser_timer.start()

    print(f"\n  qliff studio  ->  {url}")
    print("  open that URL in a browser; run results stream below. Ctrl-C to stop.\n")
    try:
        # uvicorn installs its own SIGINT/SIGTERM handlers and shuts down gracefully
        # on Ctrl-C, returning here cleanly (no traceback). timeout_graceful_shutdown
        # bounds the wait so an open WebSocket can't stall the exit.
        uvicorn.run(
            "qliff.server.app:app",
            host=args.host,
            port=args.port,
            log_level="warning",
            timeout_graceful_shutdown=5,
        )
    finally:
        if browser_timer is not None:
            browser_timer.cancel()
        print("\n  qliff studio stopped.")


if __name__ == "__main__":
    main()
