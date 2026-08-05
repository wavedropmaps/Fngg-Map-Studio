# FNGG Map Studio

Archive fortnite.gg map versions locally, and keep drop-map drawings pinned to
the map version they were actually made on.

fortnite.gg renders a saved drawing over **whatever the current map is**. A drop
map drawn in November renders on today's island, in the wrong place, and no URL
parameter changes that. This keeps every drawing tied to its version.

Python, no JDK, no build step to run it.

> Replaces the Kotlin/Compose downloader that previously lived in this repo. That
> version is still in the history — `git checkout <commit> -- src/` to pull it back.

## Running

```
run.bat
```

Installs dependencies on first run, then opens the app. Arguments pass through to
`main.py`:

| Flag | Effect |
|---|---|
| `--browser` | open in the default browser instead of a native window |
| `--no-ui` | server only, no window (for debugging) |
| `--port N` | listen on N instead of 8765 |

A busy port is stepped over automatically rather than crashing. Without
`pywebview` it falls back to the browser, so it still runs on a bare Python
install.

## The three tabs

**Maps** — download a map version (the tile scheme is detected automatically),
scan fortnite.gg for versions newer than the ones you have, and see what's
archived. Every known version shows a thumbnail of the island, because a version
number alone tells you nothing about which map it is. Several can be queued at
once.

**Drawings** — your drawings rendered by **fortnite.gg's own map UI**, over
whichever map version you archived. Their arrows, sprites and label styling; your
data; the map you choose. Edits save back to your local files. Needs internet.

**Drawings (offline)** — the same drawings in a self-contained Leaflet viewer.
Plainer, but works with no connection and doesn't care if fortnite.gg changes
their site.

Both drawing tabs share viewport presets (720p / 1080p / 2K / 4K) that lay the map
out at real pixel dimensions and scale it to fit — matching the sizes the
watermark bot renders at.

## Storage

```
~/FNGGMapDownloader/
  v38.01/
    images/{x}/{y}.jpg       native zoom-7 tiles
    _pyramid_cache/{z}/      lower zoom levels
    finalImage.png           the whole map stitched into one file (optional)
  drawings/v38.01/*.json     drawings, per map version
  _previews/                 thumbnails fetched for versions not bundled
  discovered_versions.txt    versions found by scanning
```

Unchanged from the Kotlin app, so an existing archive works with no migration.

## Why some things are the way they are

**Zoom levels are downloaded, not generated.** fortnite.gg already renders every
zoom level. The old app stitched one huge image and re-sliced it, holding a
16k–32k px image in memory to produce tiles that already existed upstream.
`finalImage.png` is still available on demand; nothing depends on it.

**Leaflet is vendored, not from a CDN.** The previous tool loaded it from unpkg,
so the "offline" viewer quietly needed internet.

**Scanning is slow and sequential on purpose.** A clean 404 is trusted at once,
but timeouts and rate-limit responses are retried with backoff — treating a
temporary block as "this version doesn't exist" silently hides real versions. The
current major is swept in full: fn.gg's numbering is sparse (41.01 is followed by
nothing until 41.20), and an early bail-out misses the tail.

**Version stats are cached.** Counting tiles and summing bytes means walking tens
of thousands of files; done naively the Maps tab stalled for ~9 s every visit.

**The Drawings tab is a proxy, not an iframe.** fortnite.gg's page is fetched
server-side and rewritten, because an iframe pointed at their origin can't be
injected into, their HTTPS page can't load `http://127.0.0.1` tiles, and their
inline `Drawing = {...}` runs before their map code — so anything injected after
load is overwritten. Serving from our own origin solves all three. See
[`app/fngg_proxy.py`](app/fngg_proxy.py).

## Bookmarklet

[`docs/fngg-tile-swap.md`](docs/fngg-tile-swap.md) — view any fortnite.gg drawing
link on an older map, straight in your browser, without this app.

## Building a standalone .exe

```
build_exe.bat
```

Produces `dist/FNGGMapStudio.exe`. CI does the same on a `v*` tag and smoke-tests
the result before publishing a release.

## Layout

```
main.py               entry point, native window / browser, port selection
app/archive.py        paths, version listing, tile lookup, cached stats
app/scanner.py        version + tile-scheme probing
app/downloader.py     tile download, optional stitch
app/fngg_proxy.py     serves fortnite.gg's UI with our drawing and tiles
app/server.py         HTTP API + background job runner
app/static/           frontend
research/             how fortnite.gg's map, tiles and drawings actually work
```

## Licence

MIT — see [LICENSE](LICENSE). Not affiliated with Epic Games or fortnite.gg.
