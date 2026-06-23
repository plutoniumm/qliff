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
    if not args.no_browser:
        # open once the server is likely up; harmless if it races slightly.
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    print(f"\n  qliff studio  ->  {url}")
    print("  open that URL in a browser; run results stream below. Ctrl-C to stop.\n")
    uvicorn.run(
        "qliff.server.app:app", host=args.host, port=args.port, log_level="warning"
    )


if __name__ == "__main__":
    main()
