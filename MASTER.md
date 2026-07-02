# MASTER.md — FNGG Map Downloader: How This Project Works

This is the deep-context doc for this repo. [README.md](README.md) is the user-facing quick
start; this file is for anyone (human or AI) about to make changes — what each piece does, why
it's built the way it is, and the specific mistakes to avoid.

## What this project actually is

Two independent tools sharing one on-disk archive format:

1. **The downloader** (`src/main/kotlin/`) — a Kotlin + Jetpack Compose for Desktop app. Given
   a Fortnite map version string (e.g. `41.01`), it pulls that version's map tiles from
   fortnite.gg tile-by-tile and stitches them into one big PNG.
2. **The Local Map Tool** (`localmaptool/`) — a Python stdlib HTTP server + Leaflet frontend
   that serves tiles the downloader already archived, with a drawing/annotation layer on top.
   It exists to fix one specific bug in fortnite.gg's own drawing tool: markers there don't
   track which map version they were drawn on, so they silently drift when the underlying map
   changes between seasons. This tool versions every drawing set explicitly instead.

Both read/write the same directory: `~/FNGGMapDownloader/`. The downloader is the only thing
that ever writes tiles there; the local map tool only ever reads them (plus writes its own
`drawings/` subtree). Neither talks to the other over a network — they're connected only by
that shared folder on disk.

**Nothing here is peer-to-peer or shared infrastructure.** The Local Map Tool binds to
`127.0.0.1` only — it serves files from *your own* `~/FNGGMapDownloader/`, nothing more. There
is no central server, no syncing between users' machines, and no searching other people's
archives. Every user has to run the downloader themselves to populate their own local copy
before the map tool has anything to show them.

## fortnite.gg tile schemes (the thing most likely to break)

fortnite.gg serves map tiles at `https://fortnite.gg/maps/{version}/{zoom}/{x}/{y}.{ext}`. There
are two schemes in the wild, and the app has to detect which one a given version uses — it
cannot be assumed:

- **Legacy**: zoom `7`, `128×128` grid, `.jpg` tiles, full resolution.
- **Newer** (recent seasons): `.webp`-only, and the zoom/grid size is *not* guaranteed to be
  7/128 — [`VersionScanner.detectTileScheme()`](src/main/kotlin/VersionScanner.kt:71) walks zoom
  levels down from 7, probing both the `(0,0)` corner tile and the far `(gridSize-1,gridSize-1)`
  corner, to find the actual zoom/grid the version serves at.

**Do not hardcode zoom=7 / grid=128 / `.jpg` anywhere new.** `FNGGDownloader` used to assume
this and it broke silently for webp-only versions. `detectScheme()` must run before
`downloadImages()`/`mergeImages()` for every version; the class's `zoomLevel`/`gridSize`/
`extension` fields exist specifically so the rest of the pipeline doesn't have to know which
scheme it's dealing with.

## Download pipeline ([`FNGGDownloader.kt`](src/main/kotlin/FNGGDownloader.kt))

`detectScheme()` → `createBaseDir()` → `downloadImages()` → `mergeImages()`, driven from
[`Main.kt`](src/main/kotlin/Main.kt)'s download button handler.

`downloadImages()` fans out one coroutine per tile (up to `gridSize²`, e.g. 16,384 for a
128×128 grid) and writes each to `~/FNGGMapDownloader/v{version}/images/{x}/{y}.{ext}`.
Two non-obvious things about how it's tuned, both fixed 2026-07-02 — see git history on this
file for the before/after:

- **Dispatcher matters more than it looks.** `Dispatchers.Default` is CPU-core-bound (a handful
  of threads) — wrong for blocking network I/O, where threads mostly sit idle on the socket.
  `Dispatchers.IO` is what blocking I/O coroutines should run on; it scales far higher.
- **`HttpURLConnection` defaults to 5 concurrent connections per host** (`http.maxConnections`
  system property). Without raising it, no amount of coroutine parallelism gets past ~5
  simultaneous tile fetches — this was the actual bottleneck, not thread count. It's set to 64
  in `downloadImages()` before any requests fire.
- A `Semaphore(48)` caps how many downloads run at once regardless of dispatcher/connection
  headroom, so the app doesn't hammer fortnite.gg hard enough to get rate-limited.

`mergeImages()` is single-threaded and reads every tile file, downscales it
(`downscaleFactor`, default 2×), and draws it into one big `BufferedImage`, then writes
`finalImage.png`. It is **not** parallelized — if this ever needs to get faster, that's the next
place to look, but note `Graphics2D`/`BufferedImage` drawing isn't thread-safe across threads
writing into the *same* image without coordination.

Both `downloadImages()` and `mergeImages()` skip work that's already on disk (file existence
checks) — re-running a download for a version that's already fully archived is a fast no-op,
not a re-download. Don't break that idempotency; it's what makes "Download" safe to click
repeatedly and what makes the local map tool's `_pyramid_cache/.done` marker pattern (see below)
consistent with how the downloader itself already behaves.

## Version discovery ([`VersionScanner.kt`](src/main/kotlin/VersionScanner.kt))

The bundled [`maps_list.txt`](src/main/resources/maps_list.txt) is a static, checked-in list of
known versions (used to populate the sidebar's map thumbnails). It goes stale every time a new
season drops. `VersionScanner.scanForNewVersions()` is the "Scan for new maps" button's backing
logic — it probes candidate version strings sequentially (300ms spacing, deliberately not
concurrent) against fortnite.gg, checking the next major version(s) first (new seasons are most
likely there) before filling in the rest of the current major. Results get cached to
`~/FNGGMapDownloader/recent_versions.txt` so a rescan isn't needed every launch.

**Why sequential and spaced, unlike the tile downloader:** this hits `fortnite.gg/maps/{version}/...`
directly (not through the archive), and speculative probing of version numbers that mostly don't
exist is a different risk profile than downloading tiles for a version you know exists — bursting
version probes is more likely to trip fortnite.gg's rate limiting for comparatively little gain
(you're guessing, not fetching known-good content). Don't naively apply the `downloadImages()`
concurrency fix here; it solves a different problem.

## Local Map Tool ([`localmaptool/server.py`](localmaptool/server.py))

Pure Python stdlib (`http.server.ThreadingHTTPServer`), no dependencies except Pillow (only
needed for the zoom pyramid, see below). Routes:

- `/api/versions` — lists `v*` folders under `~/FNGGMapDownloader/` that have an `images/`
  subdir. This is the *only* source of truth for "what versions can I view" — it does not
  consult `maps_list.txt` or fortnite.gg.
- `/tiles/{version}/{z}/{x}/{y}.ext` — serves a tile. At the archive's native zoom (`z==7`),
  it serves the original downloaded file directly. At lower zoom, it builds (once, cached) a
  downscaled tile pyramid from `finalImage.png` under `_pyramid_cache/`, guarded by a
  per-version `threading.Lock` (`_lock_for_version`) so concurrent requests for the same
  not-yet-built version don't race to build it twice, and a `.done` marker file so a restarted
  server doesn't rebuild a pyramid that already exists.
- `/api/drawings/{version}` (GET/POST/DELETE) — drawing sets are stored as one JSON file per
  `(version, name)` pair under `~/FNGGMapDownloader/drawings/{version}/{name}.json`. The version
  is part of the storage key on purpose — this is the whole point of the tool (see top of this
  file). Never collapse drawings across versions into one shared store.
- `/api/import-fgg` — the *only* outbound network call this server makes. Given a
  `fortnite.gg/map?d=...` URL, it does a plain `GET` and regex-extracts the inline
  `window.Drawing = {...}` JSON fortnite.gg renders server-side into the page HTML. No headless
  browser needed for this — the data is in the initial HTML, not injected by client JS after
  load. (`research/` has the investigation notes on this; a headless-browser approach was
  explored and abandoned as unnecessary once this was confirmed.)

Migrating a drawing set to a newer map version is a **manual, by-eye** operation in the frontend
(drag each marker to its new position) — there is deliberately no automatic image-alignment/
registration between versions, because POIs get redesigned between seasons and an automatic
transform would silently misplace things exactly as fortnite.gg's own tool does today. Don't
"fix" this by adding automatic alignment without discussing it first; it undermines the reason
this tool exists.

## Build/toolchain gotcha (read before running anything)

`build.gradle.kts` pins a **JDK 21 toolchain**
([`build.gradle.kts:18`](build.gradle.kts)), auto-provisioned via the `foojay-resolver-convention`
plugin if not already present. Two separate failure modes show up depending on what your
system's default `java` is:

1. If the *system* `java` used to launch the Gradle daemon itself is very new (JDK 25/26 as of
   this writing), **Gradle 8.8's own Kotlin-DSL script compiler can fail before your code is even
   touched** — it throws `IllegalArgumentException` out of `JavaVersion.parse()` on version
   strings it doesn't recognize (e.g. `"26"`, `"25.0.2"`). This is a Gradle-tooling problem, not
   a project code problem — it happens compiling `build.gradle.kts` itself, before `compileKotlin`
   ever runs.
2. Separately, code *compiled* against the JDK 21 toolchain produces class file version 65. Running
   those classes with anything older than JDK 21 fails with `UnsupportedClassVersionError`.

The fix for both is the same: don't rely on whatever `java` is first on `PATH`. Point `JAVA_HOME`
at a JDK the Gradle daemon itself can parse *and* that's ≥21 for running compiled output — the
project's own [`run.bat`](run.bat)/[`run.ps1`](run.ps1) already pin
`JAVA_HOME` to a Gradle-provisioned JDK 21 under `~/.gradle/jdks/...` for exactly this reason.
Use those scripts (or replicate what they do) rather than invoking `gradlew` bare on a machine
with a bleeding-edge default JDK.

## Do / Don't summary

**Do:**
- Call `detectScheme()` before any tile operation for a version you haven't touched yet.
- Keep `downloadImages()`/`mergeImages()` idempotent (skip-if-exists) — the UI and the local map
  tool's pyramid cache both depend on repeated calls being cheap no-ops.
- Keep drawing storage keyed by `(version, name)` — never merge across versions.
- Pin `JAVA_HOME` explicitly (via `run.bat`/`run.ps1` or equivalent) rather than trusting the
  system default `java` when building/running from source.
- When touching network fan-out code, think about both coroutine dispatcher *and*
  `HttpURLConnection`'s connection-pool limits — either one alone can silently cap throughput.

**Don't:**
- Don't hardcode zoom=7/grid=128/`.jpg` — always go through the detected scheme.
- Don't apply the tile-download concurrency model (high parallelism, connection pool raised) to
  `VersionScanner`'s version-probing — probing is speculative and deliberately throttled to avoid
  rate-limiting on guesses.
- Don't add automatic cross-version marker alignment to the Local Map Tool's migration flow —
  the manual, by-eye migration is intentional.
- Don't assume the Local Map Tool reaches beyond `127.0.0.1` or another user's machine — it
  can't; it only ever serves what's already in your own `~/FNGGMapDownloader/`.
- Don't use `--no-verify`/`-i` git flags or bypass the JDK toolchain pin to work around build
  friction — fix `JAVA_HOME`, don't fight the tool.
