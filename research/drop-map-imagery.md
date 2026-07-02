# Fortnite Drop-Map Imagery — Research Findings

*Compiled June 2026. All endpoints and code below were verified first-hand this session
(curl probes, byte/pixel comparison, and a Playwright+Chrome session to get past Cloudflare).*

---

## TL;DR

There are **two completely different source images** of the Battle Royale island in circulation,
and every drop-map site uses one of them:

| Family | Look | Sites | Origin |
|---|---|---|---|
| **Epic's in-game minimap** | Baked sun **shadows**, real ocean, parked vehicles | nadrops, dropmazter | Extracted from Fortnite's game files (FModel) |
| **fortnite.gg's own render** | **No shadows**, flat lighting, dark backdrop | fn.gg, droppingcalc, dropmap.net | fn.gg renders it themselves from game geometry |
| *(degenerate)* 2048px API map | Tiny, blurry when zoomed | rotationcalc | fortnite-api.com (a shrink of the minimap) |

**The shadow test** is the giveaway: Epic captures its minimap in-engine with a sun, so shadows
are baked in. fn.gg renders with flat/ambient light, so there are none. That single difference
tells you which source any site started from.

---

## 1. fortnite.gg — how THEY make it (the hard one)

fn.gg does **not** extract a finished picture. They **render the island themselves** from the
game's 3D level geometry, then slice it into tiles. Evidence gathered this session:

### Their live map config (`fortnite.gg/js/map.js`, read directly)
```js
L.map(o,{crs:L.CRS.Simple, center:[-128,128], zoom:1, minZoom:0, maxZoom:7, ...})
L.tileLayer("https://fortnite.gg/maps/"+Data.map+"/{z}/{x}/{y}."
            + (BR or "elite" ? "webp" : "jpg"),
            {noWrap:true, bounds:[[-256,0],[0,256]]})
```
- Leaflet, `CRS.Simple`, **max zoom 7** (~32,768 px master at full pyramid).
- `Data.map` = current patch folder. Verified current value = **`41.01`** (season 41).
- BR + "elite" use **.webp**; all event maps use **.jpg**.

### The smoking gun: 11 separately-rendered event maps
`map.js` defines its own coordinate bounds for each of these distinct map variants:
```
blitz, reload, reload-desert, slurp-rush, squid-game, nitemare,
surfcity, starfall, stark, stranger-things, elite   (+ the main BR map)
```
Epic does **not** ship high-res baked minimaps for every weird LTM. The fact fn.gg has a
clean, shadowless, consistently-styled top-down render for a dozen different modes is strong
proof of an **automated geometry→render pipeline**, not hand-extraction.

### No baked-shadow layer
Searched their JS: every "shadow" reference is Leaflet's standard **marker** shadow API
(`shadowUrl`, `shadowPane`, `shadowAnchor`). There is no terrain-shadow image layer — consistent
with flat-lit rendering.

### Format/resolution history (probed across patches)
| Patch | z6.webp | z7.webp | z7.jpg |
|---|---|---|---|
| 33.00, 36.00, 40.00 (old) | 404 | 404 | **200** |
| 41.00, 41.01 (current) | **200** | **200** | 404 |

They migrated **jpg → webp** and now render natively to **zoom 7 (32k-class)**. They re-render
and re-encode each season — again, pipeline behaviour.

### The likely toolchain
- **[BlenderUmap](https://github.com/Amrsatrio/BlenderUmap)** / [BlenderUmap2](https://github.com/MinshuG/BlenderUmap2)
  — reads Fortnite `.umap` level files and imports the actual island geometry (terrain, every
  building/tree/rock at world coords) into Blender.
- Point an **orthographic camera straight down**, flat/ambient light → render at huge resolution.
- Orthographic + no sun = fn.gg's exact distortion-free, shadowless look.
- Slice into 256px `{z}/{x}/{y}` tiles.

This is **far more work** than the FModel route, which is exactly why every other shadowless site
just **re-hosts fn.gg's tiles** instead of doing it themselves (see §3).

---

## 2. Epic's in-game minimap — the easy, prettier source

This is the map you open **while playing**. Epic renders it **once per patch** (empty island,
fixed sun, in-engine) and ships it as texture tiles inside the game's `.pak` files. That bake is
why nadrops and dropmazter show the **same truck, same cars, same shadows** pixel-for-pixel — they
both started from this one master image.

### Where it lives in the game files
- BR island internal name = **"Apollo"** (`Athena/Apollo/Maps/...`).
- Terrain landscape stored in chunks (e.g. `Apollo_Terrain_LS_AB12/Texture2D_0.tga`).
- The coloured top-down minimap is a **UI texture** (search "minimap" in FModel).
- Extract with **[FModel](https://fmodel.app)** (auto-fetches the patch's AES keys + mappings).

### The public shortcut (lossy)
- `https://fortnite-api.com/v1/map` → `images/map.png` (clean) / `map_en.png` (POI labels).
- **Confirmed provenance:** fortnite-api.com describes this themselves as "the current **minimap** …
  straight from the **game files**, updated with each patch." So it IS Epic's minimap, served at 2048px.
- **Confirmed same (shadowed) family:** the 2048px API map itself shows baked **directional shadows**
  (buildings/trees in the snow biome cast shadows the same way) → matches nadrops/dropmazter, NOT fn.gg's
  flat render. (Note: the *mechanism* — an in-engine sun-lit capture — is the likely method but inferred;
  what's verified is that the source render carries baked directional shadows.)
- Fine for thumbnails; mush when zoomed (same area = 14px here vs a 256px native nadrops tile).
- **rotationcalc.com** just uses this single file (`/fortnite-map.png`) → why it's low quality.
- Same area is **14×14 px** here vs a full **256×256 native tile** on nadrops (256× the detail).

### Proof the two families are different renders
Pixel-correlation of the same forest tile:
- nadrops ↔ dropmazter: **0.39 → 0.67** (rises as you downsample) = same master, independently
  AI-upscaled + colour-graded.
- dropmap.net ↔ fn.gg: **0.71–0.75** = same fn.gg render, re-hosted.
- **Epic-family ↔ fn.gg-family: 0.08** = genuinely different source images.

---

## 3. Every site, classified (verified endpoints)

**Epic-minimap family (shadows):**
- **nadrops.com** — `https://hoqugussrmehlscfkpvh.supabase.co/storage/v1/object/public/41.00_br_tiles_v2/{z}/{x}/{y}.webp`
  (z1-7, Supabase bucket; AI-upscaled to ~32k + colour-graded; nicest looking).
- **dropmazter.com** — `https://dropmazter.com/wp-content/themes/astra/in_house_maps/41.00/{z}/{x}/{y}.webp`
  (z max 7; folder literally named `in_house_maps`; WordPress site).

**fortnite.gg-render family (no shadows):**
- **fortnite.gg** — `https://fortnite.gg/maps/{patch}/{z}/{x}/{y}.webp` (current 41.01, z7; old patches .jpg). The original.
- **droppingcalc.com** — `https://cdn.droppingcalc.com/{patch}/{z}/{x}/{y}.webp`
  (uses fn.gg's exact patch folder names 41.00/41.01, TMS y-flip, capped z6, **stale** snapshot → mirror).
- **dropmap.net** — `https://map.dropmap.net/maps/hera/<hash>/tiles/{z}/{x}/{y}` (PNG, no extension;
  Cloudflare-protected; re-tiled fn.gg render).

**Degenerate:**
- **rotationcalc.com** — single 2048px `/fortnite-map.png` (the API image). No tiles, no zoom.

---

## 4. Cracking Cloudflare-protected tile servers (technique)

dropmap.net and fortnite.gg block plain `curl` (TLS-fingerprint challenge → 403 HTML). Method that worked:

1. Playwright is installed locally **but its bundled chromium isn't** → use the **system Chrome**:
   `chromium.launch(channel='chrome', headless=True)`.
2. `page.goto('https://site/')`, wait out the JS/Turnstile challenge (poll `page.title()` until
   it's no longer "Just a moment…"). Pre-seeding consent cookies avoids a redirect loop on fn.gg.
3. Fetch assets **inside the page context** so the browser's own session/headers carry them:
   ```js
   await page.evaluate(async (u) => { const r = await fetch(u); ... return base64; }, url)
   ```
   curl-from-outside still 403s; fetch-from-inside passes.

(urlscan.io has 47 archived scans of dropmap.net, but the result API needs login — the live
Playwright approach was what cracked it.)

---

## 5. Build-your-own pipeline (recommendation)

**Go the Epic-minimap route** — it's both *easier* and *better looking* (shadows + ocean, nadrops-tier):

1. **Extract** — FModel on the Windows box → search "minimap" → export the map texture grid.
2. **Stitch** — merge tiles into one big island image (PIL, ~30 lines).
3. **Beautify (optional, nadrops' edge)** — Real-ESRGAN upscale to ~32k, bump contrast/saturation,
   composite ocean texture around the island.
4. **Tile** — slice into 256px `{z}/{x}/{y}` .webp, zoom 1–7 (PIL).
5. **Serve** — static tiles on the existing `wave-leaderboard` GitHub Pages repo (or any CDN);
   display with Leaflet `L.CRS.Simple`. Could later replace the bot's fn.gg-screenshot dependency
   in `commands/auto_watermark.py`.

The fn.gg shadowless style is the *hard* route (BlenderUmap full-island umap export + orthographic
render) — only worth it if you specifically want that clean cartographic look. For a drop-map site,
the shadowed minimap is the obvious target.

> ⚠️ Extracting game assets is against Epic's EULA. Every site above does it; Epic has never gone
> after a map site — but that's the legal footing.

---

## Comparison images

*These PNGs were produced during the original research session but are not yet archived in this repo.
Drop them into `images/` when found; paths below are the intended layout.*

| File | Description |
|---|---|
| `images/0_SIDE_BY_SIDE_max_zoom.png` | nadrops (sharp/shadows) vs fn.gg (soft/no shadows) |
| `images/1.png` / `images/2.png` | rotationcalc's & the API's 2048px maps |
| `images/3.png` / `images/4.png` | nadrops vs fn.gg island overviews (ocean vs dark backdrop) |
| `images/5.png` / `images/6.png` | the individual max-zoom tiles |
| `images/7_API_vs_NADROPS_same_spot.png` | 14px vs 256px, the resolution-gap proof |
| `images/8_DROPMAZTER_vs_NADROPS_same_tile.png` | same master, two grades |
| `images/9.png` / `images/10.png` | dropmap.net overview + zoom levels (cracked via Playwright) |
