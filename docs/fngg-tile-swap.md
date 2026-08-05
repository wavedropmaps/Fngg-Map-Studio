# Viewing a fortnite.gg drawing link on an older map

fortnite.gg renders every saved drawing (`fortnite.gg/?d=YY/MM/DD/CODE`) against
**whatever the current map version is**. There is no URL parameter that changes
this:

- `?map=springfield&d=...` loads, but `?map=<variant>` swaps the tile folder *and*
  the camera bounds, so every shape lands in the wrong place.
- `?d=<different-date>/CODE` returns nothing — the date is part of the drawing's
  key, not a map selector.

But the tiles are plain static images at

```
https://fortnite.gg/maps/{version}/{z}/{x}/{y}.{jpg|webp}
```

and drawing coordinates live in Leaflet `CRS.Simple` space with bounds
`[[-256,0],[0,256]]`, which **does not change between patches** (see
[research/how-fortnite-gg-works.md](../research/how-fortnite-gg-works.md)). Only the
imagery is re-rendered each season.

So rewriting the tile image URLs in the page gives you fn.gg's own UI — labels,
arrows, legend, everything — over the map the drawing was drawn on.

## Bookmarklet

Create a bookmark whose URL is the contents of [`fngg-tile-swap.js`](fngg-tile-swap.js)
prefixed with `javascript:`. Open any `fortnite.gg/?d=...` link, then click it.

Edit `V` and `EXT` at the top to target a different version:

| Version | Extension | Map |
|---|---|---|
| `38.00` / `38.01` / `38.11` | `jpg` | Springfield (Simpsons, Nov 2025) |
| `40.10`–`40.30`, `41.00`, `41.01` | `webp` | later seasons |

Older patches are `.jpg`; fn.gg migrated to `.webp` from ~40.10 onward, so the
extension has to match the version or every tile 404s.

## Limitations

- Runs per page load — it is not persistent. Use a userscript manager if you want
  it automatic.
- Only changes what your own browser displays. Nothing is sent anywhere and the
  drawing itself is untouched.
- Depends on fn.gg keeping `img.leaflet-tile` markup; if they restructure the map,
  the selector needs updating.
- POIs were redesigned during the season, so a drawing made on `38.11` shown over
  `38.00` will be correctly *positioned* but the terrain under it will differ.
