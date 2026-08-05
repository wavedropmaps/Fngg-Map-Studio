"""FNGG Map Studio — entry point.

Starts the local server, then shows it in a native window via pywebview so this
looks and behaves like a desktop app rather than a browser tab. If pywebview
isn't installed it falls back to opening the default browser, so the app still
runs on a bare Python install.
"""
from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import webbrowser

from app import archive
from app.server import serve

TITLE = "FNGG Map Studio"


def _free_port(preferred: int) -> int:
    """Use the preferred port if we can, else let the OS pick a free one.

    Without this, a second launch (or a stale process holding the port) dies with
    an unhelpful WinError 10048 instead of just working.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=TITLE)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--browser", action="store_true",
                    help="open in the default browser instead of a native window")
    ap.add_argument("--no-ui", action="store_true",
                    help="run the server only (no window, no browser)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # serve() falls back to an OS-assigned port if this one is taken, so read the
    # port back from the bound socket rather than trusting the probe — between
    # _free_port() closing its test socket and serve() binding, anything could
    # have grabbed it.
    httpd = serve(_free_port(args.port))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"

    if not archive.list_versions():
        print("No map versions downloaded yet — use the Maps tab to grab one.")

    if args.no_ui:
        print(f"Server only. {url}   (Ctrl+C to stop)")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return 0

    if not args.browser:
        try:
            import webview  # pywebview
            webview.create_window(TITLE, url, width=1400, height=900, min_size=(900, 600))
            webview.start()
            return 0
        except ImportError:
            print("pywebview not installed — falling back to the browser.")
            print("  pip install pywebview     (for a native window)")

    webbrowser.open(url)
    print(f"{TITLE} running at {url}   (close this window to stop)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
