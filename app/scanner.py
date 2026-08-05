"""Probe fortnite.gg for available map versions and their tile scheme.

Direct port of VersionScanner.kt. The behaviour here is load-bearing and was kept
deliberately faithful:

  * A clean 404 is trusted immediately (that version really isn't there).
    Anything else -- timeout, 403, rate-limit -- is UNKNOWN and retried with
    growing backoff, because treating a temporary block as "not found" silently
    hides real versions.
  * detectTileScheme verifies BOTH corners of the grid, not just 0/0. A version
    can serve the top-left tile at a zoom it doesn't actually cover in full.
  * Scanning is fully sequential with spacing. No concurrency here on purpose:
    bursting the CDN is what triggers the rate limiting in the first place.
"""
from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0"
CONNECT_TIMEOUT = 8


class ProbeStatus(Enum):
    EXISTS = "exists"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TileScheme:
    zoom: int
    grid_size: int
    extension: str


def tile_url(version: str, zoom: int, x: int, y: int, ext: str) -> str:
    return f"https://fortnite.gg/maps/{version}/{zoom}/{x}/{y}.{ext}"


def _probe_once(url: str) -> ProbeStatus:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT) as resp:
            return ProbeStatus.EXISTS if resp.status == 200 else ProbeStatus.UNKNOWN
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return ProbeStatus.NOT_FOUND
        return ProbeStatus.UNKNOWN
    except Exception:
        return ProbeStatus.UNKNOWN


def probe_url(url: str, retries: int = 4) -> bool:
    """True if the tile exists. Retries UNKNOWN with backoff; trusts 404 at once."""
    for attempt in range(retries):
        status = _probe_once(url)
        if status is ProbeStatus.EXISTS:
            return True
        if status is ProbeStatus.NOT_FOUND:
            return False
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    logger.warning("Giving up on %s after %d attempts (rate-limited or blocked)", url, retries)
    return False


def probe_version(version: str) -> bool:
    """Does this version exist under either the legacy jpg or newer webp scheme?"""
    if probe_url(tile_url(version, 7, 0, 0, "jpg")):
        return True
    return probe_url(tile_url(version, 1, 0, 0, "webp"))


def detect_tile_scheme(version: str) -> TileScheme | None:
    """Work out the zoom, grid size and extension a version actually serves.

    Legacy versions serve full-res jpg at zoom 7 (128x128). Newer ones are
    webp-only. Rather than assume webp also caps at zoom 7, walk the zooms down
    and verify the FAR corner too, so a version that only covers a lower zoom is
    detected correctly instead of downloading a half-empty grid.
    """
    if probe_url(tile_url(version, 7, 0, 0, "jpg")):
        return TileScheme(zoom=7, grid_size=128, extension="jpg")
    time.sleep(0.3)

    for zoom in range(7, -1, -1):
        grid_size = 1 << zoom
        if not probe_url(tile_url(version, zoom, 0, 0, "webp")):
            time.sleep(0.3)
            continue
        time.sleep(0.3)
        if probe_url(tile_url(version, zoom, grid_size - 1, grid_size - 1, "webp")):
            return TileScheme(zoom=zoom, grid_size=grid_size, extension="webp")
        time.sleep(0.3)
    return None


def _scan_range(major, minors, max_consecutive_misses, counter, on_progress, on_found, results):
    """max_consecutive_misses of None means sweep the whole range, no early exit."""
    consecutive_misses = 0
    for mi in minors:
        version = f"{major}.{mi:02d}"
        counter[0] += 1
        if on_progress:
            on_progress(version, counter[0])
        if probe_version(version):
            results.append(version)
            if on_found:
                on_found(version)
            consecutive_misses = 0
        else:
            consecutive_misses += 1
            if max_consecutive_misses is not None and consecutive_misses >= max_consecutive_misses:
                break
        time.sleep(0.3)


def scan_for_new_versions(after_version: str, majors_ahead: int = 2,
                          max_consecutive_misses: int = 10,
                          on_progress=None, on_found=None) -> list[str]:
    """Probe for versions newer than `after_version` (e.g. "40.02").

    Checks the NEXT major version(s) first -- a new season is the most likely
    place for new content, so real finds surface early rather than after a long
    sweep -- then sweeps the rest of the current major.

    The current major is swept in FULL, with no early exit. fn.gg's minor numbers
    are sparse and jump hard: 41.01 is followed by nothing until 41.20, an
    18-wide hole. The original stopped after 10 consecutive misses, so it gave up
    at 41.11 and reported "nothing newer found" while 41.20 sat right there.
    A future major that doesn't exist yet still exits early -- if x.00-x.05 are
    all missing, that season hasn't shipped.
    """
    parts = after_version.split(".")
    try:
        major = int(parts[0])
    except (ValueError, IndexError):
        return []
    try:
        minor = int(parts[1])
    except (ValueError, IndexError):
        minor = 0

    results: list[str] = []
    counter = [0]

    for m in range(major + 1, major + majors_ahead + 1):
        _scan_range(m, range(0, 30), min(max_consecutive_misses, 6),
                    counter, on_progress, on_found, results)

    _scan_range(major, range(minor + 1, 60), None,
                counter, on_progress, on_found, results)

    return sorted(results)
