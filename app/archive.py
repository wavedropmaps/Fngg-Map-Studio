"""Where downloaded maps and drawings live on disk.

Deliberately the SAME layout the Kotlin app used (~/FNGGMapDownloader), so an
existing archive keeps working with no migration -- previously downloaded
versions and saved drawings are picked up on first run.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ARCHIVE_ROOT = Path.home() / "FNGGMapDownloader"
DRAWINGS_ROOT = ARCHIVE_ROOT / "drawings"

VERSION_DIR_RE = re.compile(r"^v[\d.]+$")
TILE_EXTS = ("webp", "jpg", "png")

NATIVE_ZOOM = 7
TILE_SIZE = 256


def version_dir(version: str) -> Path:
    """version may be given as "38.01" or "v38.01"."""
    name = version if version.startswith("v") else f"v{version}"
    return ARCHIVE_ROOT / name


def images_dir(version: str) -> Path:
    return version_dir(version) / "images"


def pyramid_dir(version: str, z: int | None = None) -> Path:
    d = version_dir(version) / "_pyramid_cache"
    return d if z is None else d / str(z)


def final_image(version: str) -> Path:
    """The single stitched map ("Open HQ Map" in the old GUI)."""
    return version_dir(version) / "finalImage.png"


def list_versions() -> list[str]:
    if not ARCHIVE_ROOT.is_dir():
        return []
    out = []
    for entry in ARCHIVE_ROOT.iterdir():
        if entry.is_dir() and VERSION_DIR_RE.match(entry.name) and (entry / "images").is_dir():
            out.append(entry.name)
    return sorted(out, key=lambda v: [int(p) for p in re.findall(r"\d+", v)])


# The bundled list ships with the app (ported from the old maps_list.txt);
# discovered.txt is written by "Scan for new maps" so finds survive a restart.
BUNDLED_VERSIONS = Path(__file__).parent / "data" / "known_versions.txt"
DISCOVERED_VERSIONS = ARCHIVE_ROOT / "discovered_versions.txt"


PREVIEW_DIR = Path(__file__).parent / "data" / "previews"
PREVIEW_CACHE = ARCHIVE_ROOT / "_previews"


def preview_path(version: str) -> Path | None:
    """A 256x256 thumbnail of the whole island for this version, or None.

    Three sources, cheapest first:
      1. the version's own z0 tile, if it's downloaded (no network, always right)
      2. a bundled thumbnail (the 108 shipped with the old app)
      3. a previously fetched-and-cached thumbnail
    A miss here means the caller should fetch it -- see fetch_preview().
    """
    v = version.lstrip("v")
    local = find_native_tile_at_zoom(v, 0, 0, 0)
    if local:
        return local
    for ext in ("jpg", "webp", "png"):
        p = PREVIEW_DIR / f"{v}.{ext}"
        if p.is_file():
            return p
        c = PREVIEW_CACHE / f"{v}.{ext}"
        if c.is_file():
            return c
    return None


def find_native_tile_at_zoom(version: str, z: int, x: int, y: int) -> Path | None:
    """Tile lookup that also covers the pyramid levels (find_tile, any zoom)."""
    return find_tile(version, z, x, y)


def _read_version_file(p: Path) -> list[str]:
    if not p.is_file():
        return []
    return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def known_versions() -> list[str]:
    """Every map version we know exists, downloaded or not."""
    seen = set(_read_version_file(BUNDLED_VERSIONS))
    seen.update(_read_version_file(DISCOVERED_VERSIONS))
    seen.update(v.lstrip("v") for v in list_versions())
    return sorted(seen, key=lambda v: [int(p) for p in re.findall(r"\d+", v)])


def remember_versions(versions) -> None:
    """Persist newly discovered versions so a scan only has to find them once."""
    existing = set(_read_version_file(DISCOVERED_VERSIONS))
    new = {v for v in versions if v not in existing}
    if not new:
        return
    DISCOVERED_VERSIONS.parent.mkdir(parents=True, exist_ok=True)
    with DISCOVERED_VERSIONS.open("a", encoding="utf-8") as f:
        for v in sorted(new):
            f.write(v + "\n")


_info_cache: dict[str, dict] = {}


def invalidate_info(version: str | None = None) -> None:
    """Drop cached folder stats. Call after anything writes tiles."""
    if version is None:
        _info_cache.clear()
    else:
        _info_cache.pop(version_dir(version).name, None)


def version_info(version: str, refresh: bool = False) -> dict:
    """Summary for the Maps tab: is it downloaded, how big, has a stitched image.

    Counting tiles and summing bytes means walking tens of thousands of files —
    ~2s per version on a full archive, and the original did it twice over. So:
    one pass with os.scandir, and the result is cached until a download or stitch
    invalidates it. Without this the Maps tab stalls for ~9s on every visit.
    """
    vd = version_dir(version)
    key = vd.name
    if not refresh and key in _info_cache:
        return _info_cache[key]

    imgs = images_dir(version)
    tiles = 0
    size = 0
    if vd.is_dir():
        stack = [vd]
        while stack:
            try:
                with os.scandir(stack.pop()) as it:
                    for e in it:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            size += e.stat().st_size
                            if e.path.startswith(str(imgs)):
                                tiles += 1
            except OSError:
                continue

    info = {
        "version": key,
        "downloaded": imgs.is_dir() and tiles > 0,
        "tiles": tiles,
        "bytes": size,
        "has_final_image": final_image(version).is_file(),
        "has_pyramid": (pyramid_dir(version) / ".done").is_file(),
    }
    _info_cache[key] = info
    return info


def find_native_tile(version: str, x: int, y: int) -> Path | None:
    d = images_dir(version) / str(x)
    if not d.is_dir():
        return None
    for ext in TILE_EXTS:
        p = d / f"{y}.{ext}"
        if p.is_file():
            return p
    return None


def find_tile(version: str, z: int, x: int, y: int) -> Path | None:
    """Native zoom comes from images/; everything below from the pyramid cache."""
    if z == NATIVE_ZOOM:
        return find_native_tile(version, x, y)
    if not (0 <= z < NATIVE_ZOOM):
        return None
    n = 2 ** z
    if not (0 <= x < n and 0 <= y < n):
        return None
    p = pyramid_dir(version, z) / f"{x}_{y}.jpg"
    return p if p.is_file() else None


def list_drawings(version: str) -> list[str]:
    d = DRAWINGS_ROOT / (version if version.startswith("v") else f"v{version}")
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))
