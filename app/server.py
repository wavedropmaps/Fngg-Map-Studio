"""Local HTTP server for FNGG Map Studio.

Serves the archived tiles, the drawing store, and the download/scan jobs that
used to live in the separate Kotlin GUI -- so one process backs the whole app.

Long-running work (scanning fortnite.gg, downloading a version) runs on a worker
thread and is polled via /api/job/<id>, rather than blocking a request for
minutes.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import archive
from .downloader import Cancelled, download_version, fetch_preview, stitch_final_image
from .fngg_proxy import build_page
from .scanner import detect_tile_scheme, scan_for_new_versions

logger = logging.getLogger(__name__)

STATIC_ROOT = Path(__file__).parent / "static"
PORT = 8765

# Windows' registry-backed mimetypes often lacks webp, so tiles and previews for
# newer map versions would go out as application/octet-stream.
mimetypes.add_type("image/webp", ".webp")

# fn.gg renders the drawing JSON into an inline <script> server-side, so a plain
# GET is enough -- no browser needed to read a shared drawing link.
DRAWING_RE = re.compile(r"(?:window\.)?Drawing\s*=\s*(\{.*?\});", re.DOTALL)

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _new_job(kind: str) -> str:
    jid = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[jid] = {"id": jid, "kind": kind, "state": "running", "done": 0,
                      "total": 0, "note": "", "result": None, "error": None,
                      "cancel": False, "found": []}
    return jid


def _update(jid, **kw):
    with _jobs_lock:
        if jid in _jobs:
            _jobs[jid].update(kw)


def _job(jid):
    with _jobs_lock:
        j = _jobs.get(jid)
        return dict(j) if j else None


def _cancelled(jid) -> bool:
    with _jobs_lock:
        return bool(_jobs.get(jid, {}).get("cancel"))


def fetch_fgg_drawing(fgg_url: str) -> dict:
    """Pull the Drawing JSON out of a fortnite.gg link."""
    parsed = urllib.parse.urlparse(fgg_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc.endswith("fortnite.gg"):
        raise ValueError("URL must be an http(s) fortnite.gg link")
    req = urllib.request.Request(fgg_url, headers={"User-Agent": "Mozilla/5.0 (compatible; FNGGMapStudio/1.0)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    m = DRAWING_RE.search(html)
    if not m:
        raise ValueError("No Drawing data found on that page")
    return json.loads(m.group(1))


def _run_scan(jid: str, after: str):
    try:
        _update(jid, note=f"scanning after {after}")

        def on_progress(version, checked):
            _update(jid, done=checked, note=f"probing {version}")

        def on_found(version):
            with _jobs_lock:
                if jid in _jobs:
                    _jobs[jid]["found"].append(version)

        found = scan_for_new_versions(after, on_progress=on_progress, on_found=on_found)
        if found:
            archive.remember_versions(found)   # survive a restart
        _update(jid, state="done", result={"found": found}, note="finished")
    except Exception as e:
        logger.exception("scan failed")
        _update(jid, state="error", error=str(e))


def _run_download(jid: str, version: str, stitch: bool):
    try:
        def on_progress(done, total, note):
            _update(jid, done=done, total=total, note=note)

        res = download_version(version, stitch=stitch,
                               on_progress=on_progress,
                               should_cancel=lambda: _cancelled(jid))
        archive.invalidate_info(version)
        _update(jid, state="done", result=res, note="finished")
    except Cancelled as e:
        # Partial download still changed what's on disk, so the cached stats lie.
        archive.invalidate_info(version)
        _update(jid, state="cancelled", note=str(e))
    except Exception as e:
        logger.exception("download failed")
        _update(jid, state="error", error=str(e))


def _monitor_resolution() -> tuple[int, int]:
    """Physical screen size in real pixels.

    Asked from the OS rather than the browser: JS `screen.width` is reported in
    CSS pixels, so on a scaled display (125%, 150%) it under-reports and "Native"
    would silently mean something smaller than the actual screen. Same call the
    watermark bot uses, so both agree on what Native means.
    """
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:
        return 1920, 1080


def _open_in_explorer(path: Path):
    """Open a file or folder in the OS file manager ("Open Folder" in the old GUI)."""
    if sys.platform == "win32":
        os.startfile(str(path))            # noqa: S606 - intentional, user-initiated
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep stdout clean; errors still raise

    # ── helpers ───────────────────────────────────────────────────────────────
    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type=None, immutable=False):
        if not path.is_file():
            self.send_error(404, "Not found")
            return
        content_type = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control",
                         "public, max-age=31536000, immutable" if immutable else "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _path_and_query(self):
        # Decode %20 etc. -- drawing names may contain spaces. The name patterns
        # below reject "/", so unquoting cannot open up a traversal.
        raw = self.path
        q = urllib.parse.parse_qs(raw.split("?", 1)[1]) if "?" in raw else {}
        return urllib.parse.unquote(raw.split("?", 1)[0]), q

    # ── GET ───────────────────────────────────────────────────────────────────
    def do_GET(self):
        path, query = self._path_and_query()

        if path in ("/", ""):
            return self._send_file(STATIC_ROOT / "index.html", "text/html")
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            target = (STATIC_ROOT / rel).resolve()
            if STATIC_ROOT.resolve() not in target.parents:
                self.send_error(403, "Forbidden")
                return
            return self._send_file(target)

        m = re.match(r"^/tiles/(?P<v>v[\d.]+)/(?P<z>\d+)/(?P<x>-?\d+)/(?P<y>-?\d+)\.\w+$", path)
        if m:
            tile = archive.find_tile(m["v"], int(m["z"]), int(m["x"]), int(m["y"]))
            if tile is None:
                self.send_error(404, "Tile not found")
                return
            return self._send_file(tile, immutable=True)

        if path == "/api/versions":
            return self._send_json({"versions": archive.list_versions()})

        if path == "/api/screen":
            w, h = _monitor_resolution()
            return self._send_json({"width": w, "height": h})

        if path == "/api/versions/detail":
            return self._send_json({"versions": [archive.version_info(v) for v in archive.list_versions()]})

        if path == "/api/known-versions":
            have = {v.lstrip("v") for v in archive.list_versions()}
            return self._send_json({"versions": [
                {"version": v, "downloaded": v in have} for v in archive.known_versions()
            ]})

        if path == "/api/scheme":
            v = (query.get("version") or [""])[0]
            if not v:
                return self._send_json({"error": "Missing version"}, status=400)
            s = detect_tile_scheme(v.lstrip("v"))
            return self._send_json({"scheme": None if s is None else
                                    {"zoom": s.zoom, "grid": s.grid_size, "ext": s.extension}})

        if path == "/fngg":
            # fn.gg's own UI, our drawing, our tiles.
            #   from    = which version folder the drawing is saved under
            #   version = which map version's tiles to render it over
            # These are deliberately separate: showing a drawing on a DIFFERENT
            # map than it was saved against is the whole point of this view.
            def _v(name, default):
                val = (query.get(name) or [default])[0]
                return val if val.startswith("v") else "v" + val

            version = _v("version", "v38.00")
            src_version = _v("from", version.lstrip("v"))
            name = (query.get("drawing") or [""])[0]
            src = (query.get("src") or ["https://fortnite.gg/?d=25/11/5/RfBLNktZ"])[0]
            fp = archive.DRAWINGS_ROOT / src_version / f"{name}.json"
            if not fp.is_file():
                return self._send_json(
                    {"error": f"No drawing {name!r} under {src_version}"}, status=404)
            try:
                page = build_page(src, json.loads(fp.read_text(encoding="utf-8")),
                                  f"/tiles/{version}")
            except Exception as e:
                logger.exception("fngg proxy failed")
                return self._send_json({"error": f"Proxy failed: {e}"}, status=502)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return

        m = re.match(r"^/api/preview/(?P<v>[\d.]+)$", path)
        if m:
            p = archive.preview_path(m["v"])
            if p is None:
                # Not bundled and not downloaded — pull the single z0 tile.
                try:
                    p = fetch_preview(m["v"])
                except Exception:
                    p = None
            if p is None:
                self.send_error(404, "No preview")
                return
            return self._send_file(p, immutable=True)

        m = re.match(r"^/api/job/(?P<id>\w+)$", path)
        if m:
            j = _job(m["id"])
            if j is None:
                return self._send_json({"error": "No such job"}, status=404)
            j.pop("cancel", None)
            return self._send_json(j)

        m = re.match(r"^/api/drawings/(?P<v>v[\d.]+)$", path)
        if m:
            return self._send_json({"drawings": archive.list_drawings(m["v"])})

        m = re.match(r"^/api/drawings/(?P<v>v[\d.]+)/(?P<name>[\w\-. ]+)$", path)
        if m:
            fp = archive.DRAWINGS_ROOT / m["v"] / f"{m['name']}.json"
            if not fp.is_file():
                self.send_error(404, "Drawing not found")
                return
            return self._send_file(fp, "application/json")

        if path == "/api/import-fgg":
            fgg_url = (query.get("url") or [""])[0]
            if not fgg_url:
                return self._send_json({"error": "Missing url parameter"}, status=400)
            try:
                return self._send_json({"drawing": fetch_fgg_drawing(fgg_url)})
            except ValueError as e:
                return self._send_json({"error": str(e)}, status=400)
            except urllib.error.URLError as e:
                return self._send_json({"error": f"Fetch failed: {e}"}, status=502)

        self.send_error(404, "Not found")

    # ── POST ──────────────────────────────────────────────────────────────────
    def do_POST(self):
        path, _ = self._path_and_query()

        if path == "/api/scan":
            after = (self._body().get("after") or "").strip()
            if not after:
                vs = archive.list_versions()
                after = vs[-1].lstrip("v") if vs else "40.00"
            jid = _new_job("scan")
            threading.Thread(target=_run_scan, args=(jid, after), daemon=True).start()
            return self._send_json({"job": jid, "after": after})

        if path == "/api/download":
            body = self._body()
            version = (body.get("version") or "").strip().lstrip("v")
            if not re.fullmatch(r"[\d.]+", version or ""):
                return self._send_json({"error": "Bad or missing version"}, status=400)
            jid = _new_job("download")
            threading.Thread(target=_run_download,
                             args=(jid, version, bool(body.get("stitch"))),
                             daemon=True).start()
            return self._send_json({"job": jid})

        if path == "/api/stitch":
            version = (self._body().get("version") or "").strip().lstrip("v")
            if not re.fullmatch(r"[\d.]+", version or ""):
                return self._send_json({"error": "Bad or missing version"}, status=400)
            jid = _new_job("stitch")

            def run():
                try:
                    p = stitch_final_image(
                        version,
                        on_progress=lambda d, t, n: _update(jid, done=d, total=t, note=n),
                        should_cancel=lambda: _cancelled(jid))
                    archive.invalidate_info(version)
                    _update(jid, state="done", result={"final_image": str(p)})
                except Cancelled as e:
                    _update(jid, state="cancelled", note=str(e))
                except Exception as e:
                    logger.exception("stitch failed")
                    _update(jid, state="error", error=str(e))

            threading.Thread(target=run, daemon=True).start()
            return self._send_json({"job": jid})

        m = re.match(r"^/api/job/(?P<id>\w+)/cancel$", path)
        if m:
            _update(m["id"], cancel=True)
            return self._send_json({"ok": True})

        if path == "/api/open":
            body = self._body()
            version = (body.get("version") or "").strip()
            what = body.get("what") or "folder"
            if not version:
                return self._send_json({"error": "Missing version"}, status=400)
            target = archive.final_image(version) if what == "final" else archive.version_dir(version)
            if not target.exists():
                return self._send_json({"error": f"Not found: {target}"}, status=404)
            try:
                _open_in_explorer(target)
                return self._send_json({"ok": True, "opened": str(target)})
            except Exception as e:
                return self._send_json({"error": str(e)}, status=500)

        m = re.match(r"^/api/drawings/(?P<v>v[\d.]+)/(?P<name>[\w\-. ]+)$", path)
        if m:
            data = self._body()
            out_dir = archive.DRAWINGS_ROOT / m["v"]
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"{m['name']}.json"
            out.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return self._send_json({"ok": True, "path": str(out)})

        self.send_error(404, "Not found")

    # ── DELETE ────────────────────────────────────────────────────────────────
    def do_DELETE(self):
        path, _ = self._path_and_query()
        m = re.match(r"^/api/drawings/(?P<v>v[\d.]+)/(?P<name>[\w\-. ]+)$", path)
        if not m:
            self.send_error(404, "Not found")
            return
        fp = archive.DRAWINGS_ROOT / m["v"] / f"{m['name']}.json"
        if fp.is_file():
            fp.unlink()
            return self._send_json({"ok": True})
        self.send_error(404, "Drawing not found")


def serve(port: int = PORT):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"FNGG Map Studio serving on http://127.0.0.1:{port}")
    print(f"Archive root : {archive.ARCHIVE_ROOT}")
    print(f"Versions     : {archive.list_versions()}")
    return httpd


def main():
    serve().serve_forever()


if __name__ == "__main__":
    main()
