"""Download a map version's tiles from fortnite.gg, and optionally stitch them.

Replaces FNGGDownloader.kt. Two differences from the Kotlin version, both
deliberate:

  * The zoom pyramid (z0..z6) is downloaded straight from fortnite.gg, which
    already renders every zoom level. The Kotlin app instead built one giant
    stitched image and re-sliced it, which meant holding a ~16k-32k px image in
    memory just to produce tiles that already existed upstream.
  * Stitching finalImage.png is therefore OPTIONAL. It is still offered (it is
    what "Open HQ Map" showed) but the viewer no longer depends on it, so a
    download that only feeds the map view never pays that cost.

Progress is reported through a callback so the UI can show it, and a cancel
callback is checked between tiles so a long download can be stopped.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import threading
import urllib.request
from pathlib import Path

from . import archive
from .scanner import TileScheme, detect_tile_scheme, tile_url

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; FNGGMapStudio/1.0)"
MAX_WORKERS = 24
TILE_TIMEOUT = 30
RETRIES = 3


class Cancelled(Exception):
    """Raised when the caller's cancel callback returns True mid-download."""


def _fetch(url: str) -> bytes | None:
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TILE_TIMEOUT) as r:
                return r.read()
        except Exception:
            if attempt == RETRIES - 1:
                return None
    return None


def download_version(version: str, *, scheme: TileScheme | None = None,
                     include_pyramid: bool = True,
                     stitch: bool = False,
                     on_progress=None, should_cancel=None) -> dict:
    """Download every tile for `version`.

    on_progress(done, total, note) is called as tiles land.
    should_cancel() is polled; return True from it to abort.

    Returns a summary dict. Raises Cancelled if aborted.
    """
    version = version.lstrip("v")
    scheme = scheme or detect_tile_scheme(version)
    if scheme is None:
        raise ValueError(f"No usable map tiles found for version {version}")

    ext = scheme.extension
    native_z = scheme.zoom
    grid = scheme.grid_size

    jobs: list[tuple[int, int, int]] = [(native_z, x, y) for x in range(grid) for y in range(grid)]
    if include_pyramid:
        for z in range(0, native_z):
            n = 2 ** z
            jobs += [(z, x, y) for x in range(n) for y in range(n)]

    total = len(jobs)
    lock = threading.Lock()
    state = {"done": 0, "ok": 0, "skip": 0, "fail": 0}
    cancel_flag = threading.Event()

    def dest_for(z, x, y) -> Path:
        if z == native_z:
            return archive.images_dir(version) / str(x) / f"{y}.{ext}"
        return archive.pyramid_dir(version, z) / f"{x}_{y}.jpg"

    def one(job):
        if cancel_flag.is_set():
            return
        z, x, y = job
        dest = dest_for(z, x, y)
        if dest.is_file() and dest.stat().st_size > 0:
            with lock:
                state["skip"] += 1; state["done"] += 1
            return
        # Lower zooms are fetched in this version's own extension too; fn.gg
        # serves every level in the same format for a given version.
        data = _fetch(tile_url(version, z, x, y, ext))
        with lock:
            if data:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                state["ok"] += 1
            else:
                state["fail"] += 1
            state["done"] += 1
            done = state["done"]
        if on_progress and done % 25 == 0:
            on_progress(done, total, f"z{z}")
        if should_cancel and done % 50 == 0 and should_cancel():
            cancel_flag.set()

    with cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        list(ex.map(one, jobs))

    if cancel_flag.is_set():
        raise Cancelled(f"cancelled after {state['done']}/{total} tiles")

    # Only claim the pyramid is complete if nothing failed -- a partial cache
    # would render as silent holes in the map rather than an obvious error.
    if include_pyramid and state["fail"] == 0:
        pd = archive.pyramid_dir(version)
        pd.mkdir(parents=True, exist_ok=True)
        (pd / ".done").touch()

    if on_progress:
        on_progress(total, total, "done")

    result = {
        "version": f"v{version}",
        "scheme": {"zoom": native_z, "grid": grid, "ext": ext},
        "total": total, **state,
    }

    if stitch:
        result["final_image"] = str(stitch_final_image(
            version, scheme, on_progress=on_progress))

    return result


def fetch_preview(version: str) -> Path | None:
    """Fetch and cache the z0 tile — the whole island in one 256x256 image.

    Used for versions with no bundled thumbnail (anything discovered by a scan).
    One request, so it's cheap enough to do lazily as the picker scrolls.
    """
    version = version.lstrip("v")
    existing = archive.preview_path(version)
    if existing:
        return existing

    for ext in ("jpg", "webp"):
        data = _fetch(tile_url(version, 0, 0, 0, ext))
        if data:
            archive.PREVIEW_CACHE.mkdir(parents=True, exist_ok=True)
            out = archive.PREVIEW_CACHE / f"{version}.{ext}"
            out.write_bytes(data)
            return out
    return None


def stitch_final_image(version: str, scheme: TileScheme | None = None,
                       downscale: int = 2, on_progress=None, should_cancel=None) -> Path:
    """Merge native tiles into one big PNG -- the old GUI's "Open HQ Map".

    Downscaled by `downscale` (2 by default, matching the Kotlin version): a full
    128x128 grid of 256px tiles is 32768px square, which is ~3 GB in memory as
    RGB. Halving it keeps the output usable without needing that.
    """
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None

    version = version.lstrip("v")
    scheme = scheme or detect_tile_scheme(version)
    if scheme is None:
        raise ValueError(f"No usable map tiles found for version {version}")

    grid = scheme.grid_size
    tile_px = archive.TILE_SIZE // downscale
    out_px = tile_px * grid
    canvas = Image.new("RGB", (out_px, out_px), (17, 17, 17))

    placed = 0
    for x in range(grid):
        # Checked per column, not per tile: cancelling should feel immediate but
        # a 128x128 grid means 16k checks otherwise.
        if should_cancel and should_cancel():
            canvas.close()
            raise Cancelled(f"stitch cancelled at column {x}/{grid}")
        for y in range(grid):
            p = archive.find_native_tile(version, x, y)
            if p is None:
                continue
            try:
                with Image.open(p) as im:
                    canvas.paste(im.convert("RGB").resize((tile_px, tile_px), Image.LANCZOS),
                                 (x * tile_px, y * tile_px))
                placed += 1
            except Exception:
                logger.warning("stitch: unreadable tile %s", p)
        if on_progress:
            on_progress(x + 1, grid, "stitching")

    out = archive.final_image(version)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    canvas.close()
    logger.info("stitched %s from %d tiles -> %s", version, placed, out)
    return out
