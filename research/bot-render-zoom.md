# Why the watermark render zoom is what it is (and why it looked "poor")

*Investigated June 2026 with a live, visible (headed) Playwright render + first-hand
inspection of fn.gg. This explains the long-running ">lrw / >dmw is too zoomed out /
cluttered" complaint and why it is NOT a bug.*

---

## TL;DR

The bot's render is **identical to a screenshot taken on the host machine.** The render
window is pegged to **this PC's monitor resolution (1280×720)** via `_monitor_resolution()`
in `commands/auto_watermark.py`. fn.gg's text labels are a **fixed pixel size**, so in a
narrow 1280 window they crowd the frame and the auto-fit has to sit at a lower zoom to fit
them — which reads as "zoomed out / cluttered." On a **wider** screen the exact same route
looks roomy. Nothing is wrong with the command; it faithfully reproduces this machine.

---

## The proof (headed demo)

Ran the real `>lrw` fit in a **visible** 1280×720 Chrome window. The fit zoomed out until
the route fit the window:

```
content width:  1452 → 1304 → 1250 → 1226 px   (window = 1280 px wide)
```

Final: **1226 px of content inside a 1280 px window** = content fills ~96% of the width →
cramped. The single widest element, the label *"Use launchpad to rotate to Wonkeeland and
base up on height there"*, is a fixed **587 px** — ~46% of a 1280 frame, but only ~30% of a
1920 frame. Same label, same zoom math; the **window width** is the whole difference.

## Cross-resolution live test (confirmed June 23, on the Mac)

Re-ran the live headed render on **macOS** at three different window widths and watched
the auto-fit behave. This is the direct proof that **render quality is a pure function of
window width vs fn.gg's fixed-pixel labels** — narrower window → more zoom-out → fixed-size
labels eat a bigger fraction of the frame → elements crowd and overlap → "crappier" output.

| Render width | Auto-fit behaviour | Final content | Look |
|---|---|---|---|
| **1280** (Windows host) | sits at low zoom to fit | ~1226 px in 1280 (~96%) | cramped, labels overlap |
| **1470** (this Mac, real screen @2×) | **zoomed out over 4 steps** (1713→1501→1434→**1408**) to fit the ~1418 px usable area | 1408 px | moderate |
| **1920** (the macOS fallback width) | **fit on the first step**, no zoom-out needed | 1435 px in 1920 (~75%) | roomy, orderly |

Same route, same fit math each time — **width is the only variable.** Lower resolution = the
fit has to back off further = the fixed-size labels dominate = overlap. Higher resolution =
they fit cleanly with breathing room. Confirmed empirically, not just inferred.

### macOS detection bug found while testing (scratch only — bot runtime untouched)

`_monitor_resolution()` in `commands/auto_watermark.py` is **Windows-only** (`ctypes.windll.user32`)
and silently falls back to a hardcoded **1920×1080** on any non-Windows host. So a render run on a
Mac does *not* match the Mac's real screen — it renders at the 1920 fallback. The original
`ai-hub/scratch/zoom-diag/headed_demo.py` also hardcodes the Windows `BOT_DIR` path, so it can't run
on the Mac verbatim. A Mac-runnable copy — `headed_demo_mac.py` — was added that detects the real
display via **AppKit `NSScreen`** (frame + `backingScaleFactor`) → AppleScript Finder bounds → the
`aw` fallback. This Mac reports **1470×956 @ 2×** (native 2560×1664 Retina). *(This is a diagnostic
note about the fallback path; the bot's Windows behaviour is intentional and unchanged.)*

## The two separate layers (this is the part that looks like a "conflict" but isn't)

| Layer | What controls it | Status |
|---|---|---|
| **What's in the frame** (no wasted ocean) | `window.Drawing` + Leaflet `fitBounds` — crop tight to the real route objects | ✅ fixed this session |
| **How big/cramped it looks** | the **render window width** (= host monitor) vs fn.gg's fixed-size labels | = this machine (1280) |

They stack, they don't contradict. `window.Drawing` fixed *framing*; window width sets
*apparent zoom*. And fn.gg's deep tile zoom (0–7, 32k master) is about *available detail when
zooming in* — it is NOT the limiter here. The limiter is purely the narrow render window.

## Current state (intended)

- `RENDER_W, RENDER_H = _monitor_resolution()` → tracks the host monitor (1280×720 here).
- `RENDER_DPR = _screen_dpr()` → tracks the host display scaling (1.0 here = 100%).
- Result: **render == a manual screenshot on this exact computer.** This is the chosen behaviour.

## If a roomier / less-cramped look is ever wanted

Render into a wider window than this machine's monitor — e.g. hardcode `RENDER_W,RENDER_H =
1920,1080`. A wider window → the fit zooms in further → fixed-size labels become a smaller
fraction → spacious, "big screen" look. (Tried once, reverted at owner's request to keep it
matching this PC. Do not change `RENDER_W/RENDER_H/RENDER_DPR` without explicit say-so.)

Related: [`how-fortnite-gg-works.md`](how-fortnite-gg-works.md) (CRS.Simple, tiles, `window.Drawing`).
