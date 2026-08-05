/* Drawings tab — renders YOUR drawing using fortnite.gg's own map UI.

   The page in the iframe comes from our /fngg proxy, so it is served from OUR
   origin. That is what makes this work at all:
     * same-origin, so this script can reach into the frame to read edits back
     * no mixed-content block on the local tile server
     * our script is injected ahead of fn.gg's own `Drawing = {...}` assignment

   Needs internet: fortnite.gg still serves the page shell and their scripts.
   The offline tab is the fallback. */

(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  let loadedName = null;
  let loadedFrom = null;
  let nativeScreen = [1920, 1080];   // replaced by the OS value on init

  function setStatus(msg, bad) {
    $('fnggStatus').textContent = msg || '';
    $('fnggStatus').style.color = bad ? '#e07d7d' : '#999';
  }

  async function fillVersionSelects() {
    try {
      const s = await (await fetch('/api/screen')).json();
      if (s.width && s.height) nativeScreen = [s.width, s.height];
    } catch (e) { /* keep the 1920x1080 default */ }

    let versions = [];
    try {
      versions = (await (await fetch('/api/versions')).json()).versions || [];
    } catch (e) {
      setStatus('Server unreachable', true);
      return;
    }
    for (const id of ['fnggFrom', 'fnggVersion']) {
      const sel = $(id);
      const keep = sel.value;
      sel.innerHTML = '';
      for (const v of versions) {
        const o = document.createElement('option');
        o.value = v; o.textContent = v;
        sel.appendChild(o);
      }
      if (keep && versions.includes(keep)) sel.value = keep;
      else if (versions.length) sel.value = versions[versions.length - 1];
    }
    await fillDrawings();
  }

  async function fillDrawings() {
    const from = $('fnggFrom').value;
    const sel = $('fnggDrawing');
    sel.innerHTML = '';
    if (!from) return;
    let names = [];
    try {
      names = (await (await fetch('/api/drawings/' + from)).json()).drawings || [];
    } catch (e) { /* leave empty */ }
    if (!names.length) {
      sel.innerHTML = '<option value="">(none saved on ' + from + ')</option>';
      return;
    }
    for (const n of names) {
      const o = document.createElement('option');
      o.value = n; o.textContent = n;
      sel.appendChild(o);
    }
  }

  /* Viewport presets, matching the bot's render sizes.

     The frame is laid out at REAL pixels so fn.gg's Leaflet genuinely believes it
     has that viewport (which is what changes how much map fits and where labels
     land), then scaled down visually to fit the window. Simply shrinking the
     element instead would give a different layout, not a smaller view of the
     same one. */
  function applyViewport() {
    const f = $('fnggFrame');
    const holder = $('fnggHolder');
    const choice = $('fnggViewport').value;
    const note = $('fnggScaleNote');

    if (choice === 'fit') {
      f.classList.remove('fixed');
      f.style.width = '100%';
      f.style.height = '100%';
      f.style.transform = '';
      holder.style.width = '';
      holder.style.height = '';
      note.textContent = '';
      return;
    }

    let w, h;
    if (choice === 'native') {
      // From the OS, not screen.width — the browser reports CSS pixels, which
      // under-reports on a scaled display. nativeScreen is fetched on init.
      [w, h] = nativeScreen;
    } else {
      [w, h] = choice.split('x').map(Number);
    }

    const availW = holder.clientWidth;
    const availH = holder.clientHeight;
    const scale = Math.min(availW / w, availH / h, 1);

    f.classList.add('fixed');
    f.style.width = w + 'px';
    f.style.height = h + 'px';
    f.style.transform = `scale(${scale})`;
    note.textContent = `${w}x${h} @ ${Math.round(scale * 100)}%`;
  }

  function frameUrl() {
    const p = new URLSearchParams({
      drawing: $('fnggDrawing').value,
      from: $('fnggFrom').value,
      version: $('fnggVersion').value,
    });
    return '/fngg?' + p.toString();
  }

  function load() {
    const name = $('fnggDrawing').value;
    if (!name) { setStatus('No drawing selected', true); return; }
    setStatus('Loading fortnite.gg…');
    const f = $('fnggFrame');
    f.onload = () => {
      loadedName = name;
      loadedFrom = $('fnggFrom').value;
      setStatus(`${name} on ${$('fnggVersion').value}`);
    };
    f.onerror = () => setStatus('Failed to load — are you online?', true);
    f.src = frameUrl();
    f.classList.add('on');
    $('fnggPlaceholder').style.display = 'none';
    applyViewport();
  }

  /* fn.gg's shape names -> ours. Mirrors convertFortniteDrawing() in map.js;
     kept here too so this tab works even if that file changes. */
  function fromFngg(raw) {
    const arr = (k) => raw[k] || [];
    return {
      markers: arr('marker').map((m) => ({ lat: m.latlng[0], lng: m.latlng[1], color: m.color })),
      lines: arr('polyline').map((p) => ({ latlngs: p.latlng, color: p.color })),
      boxes: arr('rectangle').map((r) => ({ bounds: [r.latlng[0], r.latlng[2]], color: r.color })),
      shapes: arr('polygon').map((p) => ({ latlngs: p.latlng, color: p.color })),
      circles: arr('circle').map((c) => ({
        lat: c.latlng[0], lng: c.latlng[1], radius: c.radius, color: c.color,
      })),
      dots: arr('circlemarker').map((c) => ({
        lat: c.latlng[0], lng: c.latlng[1], color: c.color, tooltip: c.tooltip,
      })),
    };
  }

  async function save() {
    const f = $('fnggFrame');
    if (!f.classList.contains('on') || !loadedName) {
      setStatus('Load a drawing first', true);
      return;
    }
    let raw;
    try {
      // Same-origin, so the frame's globals are readable from here.
      raw = f.contentWindow.Drawing;
    } catch (e) {
      setStatus('Could not read the frame: ' + e.message, true);
      return;
    }
    if (!raw) { setStatus('No Drawing data in the frame', true); return; }

    const converted = fromFngg(raw);
    const count = Object.values(converted).reduce((a, v) => a + v.length, 0);

    // Save against the map you were LOOKING at, which is the whole point of the
    // version pinning -- not the folder it happened to be loaded from.
    const target = $('fnggVersion').value;
    const name = loadedName;
    if (target !== loadedFrom &&
        !confirm(`Save "${name}" (${count} shapes) against ${target}?\n\n` +
                 `It was loaded from ${loadedFrom}. This writes a copy under ${target}; ` +
                 `the original is left alone.`)) {
      return;
    }
    converted.version = target;
    try {
      const r = await fetch(`/api/drawings/${target}/${encodeURIComponent(name)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(converted),
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      setStatus(`Saved ${count} shapes to ${target}/${name}`);
      if (window.reloadVersionsForMapTab) window.reloadVersionsForMapTab();
    } catch (e) {
      setStatus('Save failed: ' + e.message, true);
    }
  }

  $('fnggFrom').addEventListener('change', fillDrawings);
  $('fnggViewport').addEventListener('change', applyViewport);
  // Re-fit on window resize, otherwise a fixed viewport keeps its old scale and
  // either overflows or leaves dead space.
  window.addEventListener('resize', () => {
    if ($('fnggFrame').classList.contains('on')) applyViewport();
  });
  $('fnggLoad').addEventListener('click', load);
  $('fnggSave').addEventListener('click', save);
  $('fnggOpen').addEventListener('click', () => {
    if (!$('fnggDrawing').value) { setStatus('No drawing selected', true); return; }
    window.open(frameUrl(), '_blank');
  });

  window.initFnggTab = fillVersionSelects;
  fillVersionSelects();
})();
