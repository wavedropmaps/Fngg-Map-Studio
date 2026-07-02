# fortnite.gg Research

First-hand technical research on [fortnite.gg](https://fortnite.gg) (fn.gg) and competitor drop-map imagery, compiled June 2026.

## Documents

| Doc | What it covers |
|---|---|
| [how-fortnite-gg-works.md](how-fortnite-gg-works.md) | Site internals — Leaflet/`CRS.Simple`, tile pyramid, `window.Data`/`window.Spawns`, Cloudflare, route drawing (`window.Drawing`), 11 LTM map variants |
| [drop-map-imagery.md](drop-map-imagery.md) | Imagery lineage — Epic minimap vs fn.gg render, competitor tile URLs, pixel-correlation proof, build-your-own pipeline |
| [bot-render-zoom.md](bot-render-zoom.md) | Why `>lrw`/`>dmw` zoom looks "poor" — render window = host monitor (1280×720), so output = a screenshot taken on this PC; fixed-size fn.gg labels crowd a narrow frame. Not a bug. |

## Related live code

- **`commands/auto_watermark.py`** — `>dmw`, `>lrw`, `>zoomtest`/`>zt`, plus raw variants (`>rawdmw`, `>rawlrw`). Renders fn.gg maps via **Playwright + system Chrome** (`channel='chrome'`), reads `window.Drawing` for route framing, captures the Leaflet map via `window.__wmbMap`. The render window is the **host monitor size** (`_monitor_resolution()`) — see [bot-render-zoom.md](bot-render-zoom.md).
- **`command-trackers/drop-map-research/`** — Discord server **market** research (`>rdropmap`); different topic, but tracks the same competitor ecosystem.

## Bot memory router

Lean pointer for what the bot actually depends on from fn.gg: [`ai-hub/memory/bot-infrastructure/fortnite-gg.md`](../../memory/bot-infrastructure/fortnite-gg.md).

## Staleness warning

Season/patch numbers (e.g. `41.01`), tile URL patterns, and JS bundle behaviour **drift each season**. Re-verify endpoints in the appendix when updating anything that depends on fn.gg.

## Comparison images

The original research session produced ~11 comparison PNGs (nadrops vs fn.gg, API resolution gap, etc.). They are listed in [drop-map-imagery.md](drop-map-imagery.md) under **Comparison images** — drop files into `images/` when located; folder is reserved but empty for now.
