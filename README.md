# FNGG Map Dumper

FNGG Map Dumper is a desktop application for downloading and merging Fortnite map images from
fortnite.gg. The application is built using Kotlin and Jetpack Compose for Desktop.

The repo also includes a companion **Local Map Tool** — a Leaflet-based viewer and drawing tool
that runs against the archives this app downloads, purpose-built to fix a bug in fortnite.gg's
own drawing tool (see [Local Map Tool](#local-map-tool) below).

## Features

### Desktop downloader (Kotlin/Compose)

- Download map images for a specified Fortnite map version and merge them into one high-quality image.
- Supports both of fortnite.gg's tile schemes automatically:
  - legacy full-res `.jpg` tiles (zoom 7, 128×128 grid)
  - newer `.webp`-only tiles used by recent map versions, with automatic zoom/grid detection
    (see [`VersionScanner.kt`](src/main/kotlin/VersionScanner.kt))
- "Refresh" button scans fortnite.gg for map versions newer than the bundled list
  ([`maps_list.txt`](src/main/resources/maps_list.txt)) and adds any it finds.
- View and open downloaded maps directly from the application.

### Local Map Tool ([`localmaptool/`](localmaptool))

A local web app (Python HTTP server + Leaflet frontend) that serves the map tiles this app has
already archived to `~/FNGGMapDownloader/v{version}/images/`, and adds a versioned drawing layer
on top:

- Marker, line/route, and rectangle drawing tools on top of the archived tiles for any downloaded version.
- Every drawing set is saved tied to the exact map version it was made on (`~/FNGGMapDownloader/drawings/{version}/{name}.json`),
  so markers never silently drift onto the wrong spot when the underlying map changes between
  seasons — the one thing fortnite.gg's own drawing tool gets wrong.
- Import existing fortnite.gg drawing links (`fortnite.gg/map?d=...`) via a bookmarklet that
  copies the page's `window.Drawing` data for pasting into the tool.
- Manual migration UI: carry a drawing set forward to a newer map version by dragging each
  marker to its new position by eye (no automatic image alignment, since POIs get redesigned
  between versions).

See [`HANDOFF_local_map_tool.md`](HANDOFF_local_map_tool.md) for the full design brief, and
[`HANDOFF_camofox_browser_automation.md`](HANDOFF_camofox_browser_automation.md) for the
in-progress work on automating drawing-link import via headless browser automation.

## Requirements

- JDK 21 (auto-downloaded via the Gradle `foojay-resolver-convention` plugin if not already present)
- Gradle (via the included `gradlew`/`gradlew.bat` wrapper)
- Internet connection for downloading map images
- Python 3 (only needed to run the Local Map Tool)

## Installation

1. Download the latest release from the [Releases](../../releases) page.
2. Extract the downloaded ZIP file.
3. Run `FNGG Map Dumper.exe` to launch the application.

## Usage

### Downloader

1. Launch the application (see [Running from source](#running-from-source) if not using a release build).
2. Enter the map version you want to download, or click "Refresh" to scan for new versions.
3. Click "Download" to start downloading and merging the map images.
4. Once complete, open the map or the folder containing it directly from the app.

### Local Map Tool

1. Download at least one map version with the desktop app first (the tool serves tiles from
   the same `~/FNGGMapDownloader/v{version}/` archive).
2. Run [`run_localmaptool.bat`](run_localmaptool.bat), or `python localmaptool/server.py` directly.
3. It opens `http://127.0.0.1:8765` in your browser — pick a version, draw markers/lines/boxes,
   and save.

## Development

### Prerequisites

- IntelliJ IDEA (recommended) or any other IDE that supports Kotlin and Gradle.

### Running from source

The system JDK may not match the toolchain JDK 21 requirement. Use the provided run scripts,
which pin `JAVA_HOME` to the Gradle-provisioned JDK 21 before invoking the wrapper:

- Windows Command Prompt: `run.bat`
- PowerShell: `run.ps1`

Or open the project in IntelliJ IDEA, sync the Gradle project, and run from the IDE.

> **Note:** if your machine's default `java` is very new (e.g. JDK 25/26), Gradle 8.8's own
> Kotlin-DSL script compiler can fail to even configure the build (`JavaVersion.parse` throws on
> unrecognized version strings), independent of the JDK 21 toolchain the app itself compiles
> against. Point `JAVA_HOME` at the pinned JDK described above (`run.bat`/`run.ps1` already do
> this) rather than relying on whatever `java` resolves to on `PATH`.

### Project Structure

- `src/main/kotlin`: Main application code —
  [`Main.kt`](src/main/kotlin/Main.kt) (Compose UI),
  [`FNGGDownloader.kt`](src/main/kotlin/FNGGDownloader.kt) (download/merge pipeline),
  [`Sidebar.kt`](src/main/kotlin/Sidebar.kt) (map list/version UI),
  [`VersionScanner.kt`](src/main/kotlin/VersionScanner.kt) (probes fortnite.gg for available
  versions and tile schemes).
- `src/main/resources`: Application resources — icons, bundled map preview images, and
  `maps_list.txt` (the bundled list of known map versions).
- `localmaptool/`: Local versioned map viewer + drawing tool (Python server + Leaflet frontend),
  independent from the Kotlin app but reads its archived tile output.
- `research/`: Notes/scratch work from investigating fortnite.gg's tile and drawing-link formats.
- `build.gradle.kts` / `settings.gradle.kts`: Gradle build configuration.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Acknowledgements

- [Jetpack Compose for Desktop](https://www.jetbrains.com/lp/compose/)
- [Kotlin](https://kotlinlang.org/)
- [Gradle](https://gradle.org/)
- [Leaflet](https://leafletjs.com/)
- [Fortnite.gg](https://fortnite.gg/)
