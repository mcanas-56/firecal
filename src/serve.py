"""Start FireCal. One command:  python -m src.serve

1. Prepares the page data from data/*.csv with our pipeline (src/web_data.py: US-01
   cleaning, US-02 harmonization, US-05 season summary). Only when a CSV changed;
   otherwise it reuses data/processed/.
2. Serves web/ on http://localhost:8000 (the next free port if 8000 is taken), with
   /data/archive.json and /data/monthly.json coming from data/processed/web/.
3. Opens the browser.

Local only: it listens on 127.0.0.1 and the page makes no calls except the web fonts.

    python -m src.serve --port 8080 --no-browser
"""
from __future__ import annotations

import argparse
import errno
import functools
import http.server
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'
HOST = '127.0.0.1'
DEFAULT_PORT = 8000
GENERATED = ('archive.json', 'monthly.json')   # served at /data/<name> from data/processed/web/


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.json': 'application/json',
                      '.geojson': 'application/geo+json', '.css': 'text/css'}

    def __init__(self, *args, generated: Path | None = None, **kwargs):
        self.generated = generated
        super().__init__(*args, **kwargs)

    def translate_path(self, path):
        clean = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        for name in GENERATED:
            if clean == f'/data/{name}' and self.generated is not None:
                built = self.generated / name
                # Before the first build, answer with an explicit "no data" file, not a 404.
                return str(built if built.exists() else WEB / 'data' / 'no-data' / name)
        return super().translate_path(path)

    def end_headers(self):
        # Always serve the latest files while the team edits them.
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, format, *args):  # quiet: only errors
        if len(args) > 1 and str(args[1])[:1] in '5':
            super().log_message(format, *args)


class Server(http.server.ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second server bind a port already in use, which would
    # hide the "port taken" error that moves us to the next port.
    allow_reuse_address = sys.platform != 'win32'
    allow_reuse_port = False
    daemon_threads = True


def make_server(port: int = DEFAULT_PORT, directory: Path = WEB, generated: Path | None = None,
                tries: int = 20) -> Server:
    """Bind to `port`, or the next free one. Port 0 picks any free port."""
    if generated is None:
        from src.web_data import data_dir, web_dir
        generated = web_dir(data_dir())
    handler = functools.partial(Handler, directory=str(directory), generated=generated)
    last_error = None
    for p in ([0] if port == 0 else range(port, port + tries)):
        try:
            return Server((HOST, p), handler)
        except OSError as exc:
            if exc.errno not in (errno.EADDRINUSE, getattr(errno, 'WSAEADDRINUSE', -1), 10048):
                raise
            last_error = exc
    raise OSError(f'No free port between {port} and {port + tries - 1}') from last_error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Prepare the data and serve FireCal on localhost.')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'port to try first (default {DEFAULT_PORT})')
    parser.add_argument('--no-browser', action='store_true', help="don't open a browser tab")
    parser.add_argument('--skip-build', action='store_true', help='serve whatever data was built last')
    args = parser.parse_args(argv)

    if not (WEB / 'index.html').exists():
        print(f'web/index.html not found in {ROOT}. Run this from the FireCal repo.')
        return 1
    if not args.skip_build:
        from src.web_data import ensure
        if ensure() == 'no_data':
            get = 'py -3 scripts\\get_data.py' if sys.platform == 'win32' else 'python3 scripts/get_data.py'
            print(f'No FIRMS data in data/ yet. Download the practice set with:  {get}\n'
                  'The page opens anyway and shows the same instructions.')
    server = make_server(args.port)
    url = f'http://localhost:{server.server_address[1]}/'
    print(f'FireCal is running at {url}  (Ctrl+C to stop)', flush=True)
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
