#!/usr/bin/env python3
"""Local HTTP server for the FNGG map viewer/drawing tool.

Serves archived map tiles from ~/FNGGMapDownloader/v{version}/images/{x}/{y}.{ext}
and the static Leaflet frontend, per HANDOFF_local_map_tool.md step 1.
"""
import json
import mimetypes
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ARCHIVE_ROOT = Path.home() / "FNGGMapDownloader"
STATIC_ROOT = Path(__file__).parent / "static"
DRAWINGS_ROOT = Path.home() / "FNGGMapDownloader" / "drawings"
PORT = 8765
NATIVE_ZOOM = 7
TILE_SIZE = 256

VERSION_DIR_RE = re.compile(r"^v[\d.]+$")
TILE_EXTS = ("webp", "jpg", "png")


def list_versions():
    if not ARCHIVE_ROOT.is_dir():
        return []
    versions = []
    for entry in ARCHIVE_ROOT.iterdir():
        if entry.is_dir() and VERSION_DIR_RE.match(entry.name) and (entry / "images").is_dir():
            versions.append(entry.name)
    return sorted(versions, key=lambda v: [int(p) for p in re.findall(r"\d+", v)])


def find_native_tile(version, x, y):
    images_dir = ARCHIVE_ROOT / version / "images" / str(x)
    if not images_dir.is_dir():
        return None
    for ext in TILE_EXTS:
        candidate = images_dir / f"{y}.{ext}"
        if candidate.is_file():
            return candidate
    return None


def pyramid_cache_dir(version, z):
    return ARCHIVE_ROOT / version / "_pyramid_cache" / str(z)


_build_lock = threading.Lock()
_version_locks = {}


def _lock_for_version(version):
    with _build_lock:
        lock = _version_locks.setdefault(version, threading.Lock())
    return lock


def ensure_pyramid_built(version):
    done_marker = ARCHIVE_ROOT / version / "_pyramid_cache" / ".done"
    if done_marker.is_file():
        return True

    lock = _lock_for_version(version)
    with lock:
        if done_marker.is_file():
            return True

        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None

        final_image = ARCHIVE_ROOT / version / "finalImage.png"
        if not final_image.is_file():
            return False

        with Image.open(final_image) as img:
            current = img.convert("RGB")
            for z in range(NATIVE_ZOOM - 1, -1, -1):
                size = TILE_SIZE * (2 ** z)
                current = current.resize((size, size), Image.LANCZOS)
                cache_dir = pyramid_cache_dir(version, z)
                cache_dir.mkdir(parents=True, exist_ok=True)
                n = 2 ** z
                for tx in range(n):
                    for ty in range(n):
                        box = (tx * TILE_SIZE, ty * TILE_SIZE, (tx + 1) * TILE_SIZE, (ty + 1) * TILE_SIZE)
                        current.crop(box).save(cache_dir / f"{tx}_{ty}.jpg", quality=85)

        done_marker.parent.mkdir(parents=True, exist_ok=True)
        done_marker.touch()
    return True


def find_tile(version, z, x, y):
    if z == NATIVE_ZOOM:
        return find_native_tile(version, x, y)

    if not (0 <= z < NATIVE_ZOOM):
        return None

    n = 2 ** z
    if not (0 <= x < n and 0 <= y < n):
        return None

    if not ensure_pyramid_built(version):
        return None

    tile_path = pyramid_cache_dir(version, z) / f"{x}_{y}.jpg"
    return tile_path if tile_path.is_file() else None


DRAWING_RE = re.compile(r"(?:window\.)?Drawing\s*=\s*(\{.*?\});", re.DOTALL)


def fetch_fgg_drawing(fgg_url):
    """Fetch a fortnite.gg map URL and extract the server-rendered Drawing JSON.

    The `Drawing={...}` object is rendered directly into an inline <script>
    tag in the page HTML (not injected by client-side JS after load), so a
    plain HTTP GET is sufficient -- no browser/JS execution needed.
    """
    parsed = urllib.parse.urlparse(fgg_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc.endswith("fortnite.gg"):
        raise ValueError("URL must be an http(s) fortnite.gg link")

    req = urllib.request.Request(
        fgg_url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; FNGGMapDownloader/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    m = DRAWING_RE.search(html)
    if not m:
        raise ValueError("No Drawing data found on that page")
    return json.loads(m.group(1))


def list_drawings(version):
    version_dir = DRAWINGS_ROOT / version
    if not version_dir.is_dir():
        return []
    return sorted(p.stem for p in version_dir.glob("*.json"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep stdout clean; errors still raise

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type=None, immutable=False):
        if not path.is_file():
            self.send_error(404, "Not found")
            return
        content_type = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if immutable:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/" or path == "":
            return self._send_file(STATIC_ROOT / "index.html", "text/html")

        if path == "/api/versions":
            return self._send_json({"versions": list_versions()})

        m = re.match(r"^/tiles/(?P<version>v[\d.]+)/(?P<z>\d+)/(?P<x>-?\d+)/(?P<y>-?\d+)\.\w+$", path)
        if m:
            z, x, y = int(m.group("z")), int(m.group("x")), int(m.group("y"))
            tile = find_tile(m.group("version"), z, x, y)
            if tile is None:
                self.send_error(404, "Tile not found")
                return
            return self._send_file(tile, immutable=True)

        m = re.match(r"^/api/drawings/(?P<version>v[\d.]+)$", path)
        if m:
            return self._send_json({"drawings": list_drawings(m.group("version"))})

        if path == "/api/import-fgg":
            query = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            fgg_url = (query.get("url") or [""])[0]
            if not fgg_url:
                return self._send_json({"error": "Missing url parameter"}, status=400)
            try:
                drawing = fetch_fgg_drawing(fgg_url)
            except ValueError as e:
                return self._send_json({"error": str(e)}, status=400)
            except urllib.error.URLError as e:
                return self._send_json({"error": f"Fetch failed: {e}"}, status=502)
            return self._send_json({"drawing": drawing})

        m = re.match(r"^/api/drawings/(?P<version>v[\d.]+)/(?P<name>[\w\-. ]+)$", path)
        if m:
            file_path = DRAWINGS_ROOT / m.group("version") / f"{m.group('name')}.json"
            if not file_path.is_file():
                self.send_error(404, "Drawing not found")
                return
            return self._send_file(file_path, "application/json")

        # static assets (js/css)
        safe_rel = path.lstrip("/")
        candidate = (STATIC_ROOT / safe_rel).resolve()
        if STATIC_ROOT.resolve() in candidate.parents and candidate.is_file():
            return self._send_file(candidate)

        self.send_error(404, "Not found")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        m = re.match(r"^/api/drawings/(?P<version>v[\d.]+)/(?P<name>[\w\-. ]+)$", path)
        if not m:
            self.send_error(404, "Not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        version_dir = DRAWINGS_ROOT / m.group("version")
        version_dir.mkdir(parents=True, exist_ok=True)
        out_path = version_dir / f"{m.group('name')}.json"
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self._send_json({"ok": True, "path": str(out_path)})

    def do_DELETE(self):
        path = self.path.split("?", 1)[0]
        m = re.match(r"^/api/drawings/(?P<version>v[\d.]+)/(?P<name>[\w\-. ]+)$", path)
        if not m:
            self.send_error(404, "Not found")
            return
        file_path = DRAWINGS_ROOT / m.group("version") / f"{m.group('name')}.json"
        if file_path.is_file():
            file_path.unlink()
            return self._send_json({"ok": True})
        self.send_error(404, "Drawing not found")


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"FNGG local map tool running at http://127.0.0.1:{PORT}")
    print(f"Archive root: {ARCHIVE_ROOT}")
    print(f"Versions found: {list_versions()}")
    server.serve_forever()


if __name__ == "__main__":
    main()
