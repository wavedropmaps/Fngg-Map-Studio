# How fortnite.gg Works — Extensive Technical Teardown

*Compiled June 2026 from first-hand inspection of fn.gg's live site, its JavaScript bundles
(`map.js`, `map-lib.js`, `global.js`), and its data files (`data/en.js`, `data/spawns.js`),
fetched via curl + a Playwright/Chrome session to get past Cloudflare. Current state: season 41,
map version `41.01`.*

---

## 0. TL;DR

fortnite.gg is a **vanilla-JS** (no React/Vue) interactive map built on a **customized Leaflet**
fork. The island is **not** a live 3D scene — it's a **pre-rendered raster image** sliced into a
`{z}/{x}/{y}` tile pyramid and served as static files from fn.gg's own domain. Everything dynamic
(POIs, chests, spawns, routes) is **vector markers** drawn *on top* of those tiles from JSON-ish
data files. The base imagery is **rendered by fn.gg themselves** from extracted game geometry
(flat-lit, orthographic, **no baked shadows**) — which is what distinguishes it from the
Epic-minimap sites (nadrops, dropmazter).

---

## 1. Tech stack & delivery

| Layer | What fn.gg uses |
|---|---|
| Frontend | **Plain JavaScript**, jQuery-ish `$()` helper, no SPA framework |
| Map engine | **Leaflet**, customized & minified into `js/map-lib.js` (~269 KB) — bundles Leaflet core + **Leaflet.markercluster** + **Supercluster** |
| App logic | `js/map.js` (~29 KB) — the map page controller |
| Shared site code | `js/global.js` (~31 KB) — L10N, tooltips, sidebar, ads, modals, voting |
| Data | `data/en.js` (per-language) + `data/spawns.js` — plain `window.Data` / `window.Spawns` globals |
| Base map tiles | Static files at `fortnite.gg/maps/{patch}/{z}/{x}/{y}.{webp|jpg}` |
| Marker icons | Static PNGs at `fortnite.gg/icons/{id}.png` |
| Edge / anti-bot | **Cloudflare** (Turnstile challenge, `cdn-cgi/challenge-platform`) |
| Monetization | Google **AdSense** (`adsbygoogle`), **hadronid** (`cdn.hadronid.net` — ad identity) |
| Versioning | Cache-busting `?v=<unix-timestamp>` on every JS/data file |

**Why it loads fast:** the map is just static image tiles + a few JS/JSON files behind Cloudflare's
CDN. No server-side rendering, no database calls on map view. The only "API" calls are for
side features (`/item-details`, `/cosmetics`, `/drawings?vote=`, `/account`).

---

## 2. The map rendering system (the core)

### Leaflet setup (verbatim from `map.js`)
```js
let g = L.canvas();
T = L.map(o, {
  crs: L.CRS.Simple,        // flat pixel CRS, not geographic
  center: [-128, 128],
  zoom: 1, minZoom: 0, maxZoom: 7,
  zoomSnap: 0,              // smooth fractional zoom
  preferCanvas: true,       // markers drawn on a canvas renderer (perf)
  renderer: g, ...
});
L.tileLayer(
  "https://fortnite.gg/maps/" + Data.map + "/{z}/{x}/{y}." +
    (mainBRorElite ? "webp" : "jpg"),
  { noWrap: true, bounds: [[-256, 0], [0, 256]] }
).addTo(T);
```

### Key properties
- **CRS.Simple** — the map is a flat image, not lat/long. Coordinates are raw pixel/game units.
- **Coordinate space:** the world spans `[[-256,0],[0,256]]` in Leaflet units. All marker `coords`
  in the data files live in this same space (e.g. a chest at `[-170.79, 54.97]`). No projection math.
- **Tile pyramid:** 256 px tiles, zoom **0–7**. Full pyramid at z7 = a **32,768 × 32,768 px** master
  (128×128 tiles). Standard slippy-map `{z}/{x}/{y}` addressing.
- **Format split:** main BR map + the "elite" mode use **`.webp`**; all other event maps use **`.jpg`**.
- **Patch folders:** `Data.map` is the version string (currently `41.01`). Each patch/season gets a
  fresh folder — the map is **re-rendered every update**.

### Resolution history (probed across patches)
| Patch | z6.webp | z7.webp | z7.jpg |
|---|---|---|---|
| 33.00 / 36.00 / 40.00 (old) | ❌ | ❌ | ✅ |
| 41.00 / 41.01 (current) | ✅ | ✅ | ❌ |

They **migrated jpg → webp** and now render natively to **zoom 7 (32k)**. Evidence of an evolving,
automated pipeline rather than a one-off asset.

---

## 3. How fn.gg produces the base imagery (the differentiator)

fn.gg does **not** extract Epic's in-game minimap. They **render the island themselves**. Evidence:

1. **No baked shadows.** The Epic minimap (used by nadrops/dropmazter) has directional sun shadows
   baked in — buildings/trees cast shadows. fn.gg's render is **flat-lit** with none. Searching their
   JS, every "shadow" reference is Leaflet's *marker* shadow API, not terrain.
2. **Orthographic, distortion-free top-down** — the hallmark of a rendered camera, not a screenshot.
3. **The smoking gun — 11 separate event-map renders.** `map.js` carries its own coordinate bounds
   for each of these distinct map variants:
   ```
   blitz, reload, reload-desert, slurp-rush, squid-game, nitemare,
   surfcity, starfall, stark, stranger-things, elite   (+ main BR)
   ```
   Each is loaded as `fortnite.gg/maps/<variant-or-patch>/{z}/{x}/{y}`. Epic does **not** ship
   baked high-res minimaps for random LTMs — so fn.gg must be generating these from game data with
   an **automated pipeline**.

### The likely toolchain
- **[BlenderUmap](https://github.com/Amrsatrio/BlenderUmap) / [BlenderUmap2](https://github.com/MinshuG/BlenderUmap2)**
  — reads Fortnite `.umap` level files and rebuilds the island geometry (terrain + every placed
  building/tree/rock at world coords) inside Blender.
- Point an **orthographic camera straight down**, light it flat/ambient → render at huge resolution.
- Orthographic + no sun = fn.gg's exact look.
- Slice into 256 px `{z}/{x}/{y}` tiles, encode webp.

*(This is an informed inference about mechanism — BlenderUmap is the standard public tool for exactly
this. What's verified: the render is flat-lit/shadowless, orthographic, exists for a dozen LTM
variants, and is re-rendered each patch.)*

**Why this matters:** it's far more work than the FModel "extract the minimap" route — which is
precisely why the *other* shadowless sites (droppingcalc, dropmap.net) don't do it themselves; they
just re-host fn.gg's finished tiles.

---

## 4. Data layer (markers, spawns, POIs)

The map's interactive content is plain global objects loaded from `/data/`:

```js
window.Data = {
  "season": 41,
  "map": "41.01",
  "data": {
    "spawns": { "name":"Spawns", "sub": {
        "extraction_sites": { "cluster":true, "name":"Extraction Sites",
                              "menu_icon":1629, "markers":[{ "icon":1629, "coords":[[-148.29,190.73], ...] }] },
        "chests":        { "cluster":true, "menu_icon":3,    "markers": Spawns.chests },
        "rare_chests":   { "cluster":true, "menu_icon":1326, "markers": Spawns.rare_chests },
        "ammo_boxes": ..., "vending_machines": ..., "launchpads": ...,
        "cars_sport": ..., "cars_suv": ..., "boats": ..., "fishing_holes": ...,
        "cash_registers": ..., "bushes": ..., "dumpsters": ...   // 25+ categories
    }},
    "poi": {...}, "landmarks": {...}, "chests": {...}, "quests": {...}
  }
};
window.Spawns = { "chests":[{ "icon":2, "coords":[[...],[...]] }], "rare_chests":[...], ... };
```

- **Two-file split:** `data/en.js` holds the *structure* + labels (localized — there's a language
  picker, so `data/<lang>.js` per language); `data/spawns.js` holds the bulk **coordinate arrays**,
  referenced by name (`Spawns.chests`) to keep the localized file small.
- **Marker categories (25+):** extraction sites, chests, rare chests, ammo boxes, vending/mending
  machines, launch pads, cars (Whiplash/TrailSmasher), boats, off-road tires, service stations,
  campfires, noms, mushrooms, slurp barrels/trucks, fishing rods/holes, jobboards, safes, cash
  registers, bushes, dumpsters, …
- **Icons:** each marker has a numeric `icon` id → image at `fortnite.gg/icons/{id}.png`
  (`L.icon({iconUrl:"/icons/"+c.icon+".png"})`). Optional `icon2` for a second state.
- **Coordinates** are already in Leaflet CRS.Simple space — no transform needed. (Contrast dropmazter,
  which stores world units and converts `3000 world units = 256 leaflet units`.)

---

## 5. Map features & interactions

- **Clustering:** `markercluster` + **Supercluster** (`radius:40, extent:512, nodeSize:64`) collapse
  thousands of spawn markers into counts at low zoom, expanding as you zoom in. Categories flagged
  `"cluster":true` opt in.
- **Canvas rendering:** `preferCanvas:true` + a shared `L.canvas()` renderer draws markers on canvas
  (not DOM) for performance with huge marker counts; a throttled `drag` handler re-renders at ~30 fps.
- **Route / drawing tools:** `map.js` draws polylines with arrow markers (`arrowIcon`, computed
  bearing via `atan2`), supports community "drawings" with a voting endpoint (`/drawings?vote=`),
  tunnels/cube-step paths, etc.
- **Sidebar + selection state:** category toggles persist in `localStorage`
  (`fngg_selected`, `fngg_opened`, `fngg_season`); state resets when the season changes.
- **Map variant switch:** `?map=<variant>` query param swaps tile folder + camera bounds (e.g.
  `?map=reload`, `?map=blitz`).
- **L10N:** `global.js` holds an `L10N[]` string table + language selector; tooltips, YouTube-link
  icons, llama/loot modals, etc.

---

## 6. Anti-bot, consent & monetization

- **Cloudflare Turnstile** guards the HTML pages — a plain `curl` of `/?map` returns the
  "Just a moment…" challenge page; the **static JS/tiles are NOT challenged** (curl fetches them
  fine). A consent cookie is needed or the map URL redirect-loops.
- **To script it:** drive real Chrome (`playwright chromium.launch(channel='chrome')`), wait out the
  challenge, then `fetch()` assets *inside* the page context so the browser's session carries them.
- **Ads:** Google AdSense + `hadronid` identity script; `resizeAds()` in global.js manages slots.

---

## 7. How the copycats relate to fn.gg

- **droppingcalc.com** re-hosts fn.gg's tiles on `cdn.droppingcalc.com/{patch}/{z}/{x}/{y}.webp` —
  same fn.gg patch-folder names (`41.00`/`41.01`), TMS y-flip, capped at z6, and a **stale** snapshot.
- **dropmap.net** re-tiles fn.gg's render at `map.dropmap.net/maps/hera/<hash>/tiles/{z}/{x}/{y}`
  (PNG, Cloudflare-protected). Pixel-correlates **0.71–0.75** with fn.gg vs **0.08** with the
  Epic-minimap family — i.e. unmistakably fn.gg's imagery.
- The "fnmap" scraper ([github.com/crypoxyz/fnmap](https://github.com/crypoxyz/fnmap)) downloads
  fn.gg's tiles and stitches them up to 16k — the easy way to grab fn.gg's render (their bandwidth).

---

## 8. To replicate fn.gg yourself

**If you want fn.gg's exact shadowless style (hard):**
1. Extract the island `.umap`(s) with FModel/CUE4Parse.
2. Import geometry via BlenderUmap2 into Blender.
3. Orthographic top-down camera, flat/ambient light, render at ~16–32k.
4. Slice into 256px `{z}/{x}/{y}` webp (PIL/`vips dzsave`), zoom 0–7.
5. Serve static; display with Leaflet `L.CRS.Simple`, bounds `[[-256,0],[0,256]]`.
6. Overlay markers from your own JSON in the same coordinate space.

**Easier + arguably prettier (the Epic-minimap route):** skip the render — FModel-export Epic's
in-game minimap (has shadows + ocean, nadrops-tier), upscale/grade, tile the same way. See
[drop-map-imagery.md](drop-map-imagery.md) for that pipeline and the full multi-site comparison.

> ⚠️ Extracting game assets is against Epic's EULA. Every site here does it; Epic has not pursued
> map sites — but that's the legal footing.

---

## Appendix — verified endpoints
- Tiles: `https://fortnite.gg/maps/41.01/{z}/{x}/{y}.webp` (z0–7; old patches `.jpg`)
- Marker icons: `https://fortnite.gg/icons/{id}.png`
- Data: `https://fortnite.gg/data/en.js` (`window.Data`), `https://fortnite.gg/data/spawns.js` (`window.Spawns`)
- Scripts: `https://fortnite.gg/js/{map,map-lib,global}.js`
- Map variants: `?map=blitz|reload|reload-desert|slurp-rush|squid-game|nitemare|surfcity|starfall|stark|stranger-things|elite`
- Current: season 41, map `41.01`
