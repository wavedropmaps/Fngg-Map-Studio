"""Serve fortnite.gg's own map UI, rendering OUR drawing over OUR map tiles.

Why a proxy rather than an iframe or a bookmarklet:

  * An iframe pointed straight at fortnite.gg is cross-origin, so we could not
    inject anything into it, and their headers may refuse framing outright.
  * fn.gg is https, our tile server is http://127.0.0.1 -- mixed content, which
    Chrome blocks (verified: the request just hangs).
  * fn.gg assigns `Drawing = {...}` in an inline <script> that runs before their
    map code reads it, so anything injected after load is overwritten.

Fetching the page server-side and rewriting it solves all three: the result is
served from our own origin (so same-origin, no mixed content, and we can inject
anything), and we control exactly where our script lands in the document -- ahead
of their assignment, which we then swallow with an accessor.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request

logger = logging.getLogger(__name__)

FNGG = "https://fortnite.gg"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# Our saved format -> fn.gg's. The inverse of convertFortniteDrawing() in map.js.
def to_fngg_format(d: dict) -> dict:
    out: dict[str, list] = {"polyline": [], "polygon": [], "rectangle": [],
                            "circle": [], "marker": [], "circlemarker": []}
    for m in d.get("markers") or []:
        out["marker"].append({"color": m.get("color"), "latlng": [m["lat"], m["lng"]]})
    for l in d.get("lines") or []:
        out["polyline"].append({"color": l.get("color"), "latlng": l["latlngs"]})
    for s in d.get("shapes") or []:
        out["polygon"].append({"color": s.get("color"), "latlng": s["latlngs"]})
    for c in d.get("circles") or []:
        out["circle"].append({"color": c.get("color"), "radius": c.get("radius"),
                              "latlng": [c["lat"], c["lng"]]})
    for c in d.get("dots") or []:
        e = {"color": c.get("color"), "latlng": [c["lat"], c["lng"]]}
        if c.get("tooltip"):
            e["tooltip"] = c["tooltip"]
        out["circlemarker"].append(e)
    for b in d.get("boxes") or []:
        # We store two opposite corners; fn.gg wants all four, in order.
        (la1, lo1), (la2, lo2) = b["bounds"]
        out["rectangle"].append({"color": b.get("color"),
                                 "latlng": [[la1, lo1], [la2, lo1], [la2, lo2], [la1, lo2]]})
    return out


_INJECT = """
<base href="{fngg}/">
<script>
(function () {{
  /* 1. Pin OUR drawing. fn.gg's own inline assignment lands on the setter below
        and is discarded, so their renderer reads ours instead. */
  var ours = {drawing};
  var current = ours;
  try {{
    Object.defineProperty(window, 'Drawing', {{
      configurable: false,
      get: function () {{ return current; }},
      set: function (_v) {{ /* keep ours */ }}
    }});
  }} catch (e) {{ window.Drawing = ours; }}

  /* 2. Point base-map tiles at our local archive. Same origin as this page, so
        no mixed-content block. Leaflet creates tiles lazily and reuses some by
        reassigning src, hence watching childList AND the src attribute. */
  /* Must be absolute. The <base href> above points at fortnite.gg, so a
     root-relative "/tiles/..." would resolve to THEIR origin and 404. */
  var LOCAL = location.origin + {local!r};
  var RE = /\\/maps\\/[\\d.]+\\/(\\d+)\\/(-?\\d+)\\/(-?\\d+)\\.(?:jpg|webp)/;
  function swap(img) {{
    if (!img || !img.src) return;
    var m = img.src.match(RE);
    if (!m) return;
    var url = LOCAL + '/' + m[1] + '/' + m[2] + '/' + m[3] + '.img';
    if (img.src !== url) img.src = url;
  }}
  function sweep() {{ document.querySelectorAll('img').forEach(swap); }}
  new MutationObserver(function (muts) {{
    muts.forEach(function (mu) {{
      if (mu.type === 'attributes') {{ swap(mu.target); return; }}
      mu.addedNodes.forEach(function (n) {{
        if (n.tagName === 'IMG') swap(n);
        else if (n.querySelectorAll) n.querySelectorAll('img').forEach(swap);
      }});
    }});
  }}).observe(document.documentElement,
              {{childList: true, subtree: true, attributes: true, attributeFilter: ['src']}});
  document.addEventListener('DOMContentLoaded', sweep);
  window.addEventListener('load', sweep);
}})();
</script>
"""


def is_fngg_url(url: str) -> bool:
    """True only for https://fortnite.gg or a *.fortnite.gg subdomain.

    A plain endswith("fortnite.gg") also accepts evilfortnite.gg, and matching on
    netloc rather than hostname trips over userinfo and ports.
    """
    try:
        p = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    return host == "fortnite.gg" or host.endswith(".fortnite.gg")


def build_page(source_url: str, drawing: dict, tile_base: str) -> bytes:
    """Fetch an fn.gg map page and rewrite it to use our drawing and tiles.

    tile_base is an absolute path on THIS server, e.g. "/tiles/v38.00".
    """
    # Hard gate. Without it this is an arbitrary fetcher: file:// reads local
    # files straight back to the caller, and any http(s) URL turns the app into
    # an open proxy and an SSRF pivot onto the user's own network.
    if not is_fngg_url(source_url):
        raise ValueError("source must be an http(s) fortnite.gg URL")

    req = urllib.request.Request(source_url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        html = r.read().decode("utf-8", errors="replace")

    # json.dumps does NOT escape "</", so a tooltip containing "</script>" closes
    # this block early and everything after it becomes live markup on our own
    # origin. Tooltips come from imported fortnite.gg links, i.e. from whoever
    # shared the link -- untrusted. Escaping the slash keeps the JSON identical
    # to the parser while making the sequence impossible to emit.
    payload = json.dumps(to_fngg_format(drawing)).replace("</", "<\\/")
    inject = _INJECT.format(fngg=FNGG, drawing=payload, local=tile_base)

    # Land the injection immediately after <head> so it precedes every fn.gg
    # script -- including the inline `Drawing = {...}` we need to override.
    m = re.search(r"<head[^>]*>", html, re.IGNORECASE)
    if m:
        html = html[:m.end()] + inject + html[m.end():]
    else:
        html = inject + html

    return html.encode("utf-8")
