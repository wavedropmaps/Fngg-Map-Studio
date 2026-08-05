const WORLD_BOUNDS = [[-256, 0], [0, 256]];
const NATIVE_ZOOM = 7;
const FNGG_YELLOW = "#fce51e";
// fn.gg's circlemarkers carry no radius (it's a fixed-size screen dot), so pick one.
const DOT_RADIUS_PX = 5;
// fn.gg shows label text permanently in the shape's own colour, not on hover.
const LABEL_OPTS = { permanent: true, direction: "right", className: "fngg-label", offset: [6, 0] };

function labelFor(text, color) {
  // Build as a DOM node rather than an HTML string: label text comes from the
  // fn.gg drawing and is not ours to trust as markup.
  const span = document.createElement("span");
  span.textContent = text;
  span.style.color = color || FNGG_YELLOW;
  return span;
}

const state = {
  version: null,
  drawingName: null,
  map: null,
  drawnItems: null,
  drawControl: null,
};

// Same pin path/viewBox fortnite.gg's own map uses (from their map.js), so
// markers here match the site instead of the default Leaflet teardrop icon.
function fnggMarkerIcon(color) {
  return L.divIcon({
    className: "fngg-marker-icon",
    iconSize: [30, 30],
    iconAnchor: [15, 30],
    tooltipAnchor: [15, -15],
    html: `<svg width="30" height="30" viewBox="0 0 24 24" style="fill:${color || FNGG_YELLOW};stroke:#000"><path d="M12 0c-4.198 0-8 3.403-8 7.602 0 4.198 3.469 9.21 8 16.398 4.531-7.188 8-12.2 8-16.398 0-4.199-3.801-7.602-8-7.602zm0 11c-1.657 0-3-1.343-3-3s1.343-3 3-3 3 1.343 3 3-1.343 3-3 3z"/></svg>`,
  });
}

function tileLayerFor(version) {
  return L.tileLayer(`/tiles/${version}/{z}/{x}/{y}.img`, {
    minZoom: 0,
    maxZoom: NATIVE_ZOOM,
    maxNativeZoom: NATIVE_ZOOM,
    noWrap: true,
    bounds: WORLD_BOUNDS,
    tileSize: 256,
  });
}

function initMap() {
  const map = L.map("map", {
    crs: L.CRS.Simple,
    minZoom: 0,
    maxZoom: NATIVE_ZOOM,
    attributionControl: false,
  });
  map.fitBounds(WORLD_BOUNDS);

  const drawnItems = new L.FeatureGroup();
  map.addLayer(drawnItems);

  const drawControl = new L.Control.Draw({
    edit: { featureGroup: drawnItems },
    draw: {
      marker: { icon: fnggMarkerIcon(FNGG_YELLOW) },
      polyline: {},
      rectangle: {},
      polygon: false,
      circle: false,
      circlemarker: false,
    },
  });
  map.addControl(drawControl);

  map.on(L.Draw.Event.CREATED, (e) => {
    if (e.layer instanceof L.Marker) e.layer.options.color = FNGG_YELLOW;
    drawnItems.addLayer(e.layer);
  });

  state.map = map;
  state.drawnItems = drawnItems;
  state.drawControl = drawControl;
}

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

function setStatus(msg) {
  document.getElementById("status").textContent = msg;
  if (msg) setTimeout(() => { document.getElementById("status").textContent = ""; }, 4000);
}

async function loadVersions() {
  const { versions } = await fetchJSON("/api/versions");
  const selects = ["versionSelect", "importVersion", "migrateVersion"].map((id) => document.getElementById(id));
  for (const sel of selects) {
    sel.innerHTML = "";
    for (const v of versions) {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    }
  }
  return versions;
}

function setTileLayer(version) {
  if (state.currentTileLayer) state.map.removeLayer(state.currentTileLayer);
  state.currentTileLayer = tileLayerFor(version);
  state.currentTileLayer.addTo(state.map);
}

async function loadDrawingList(version) {
  const sel = document.getElementById("drawingSelect");
  sel.innerHTML = '<option value="">(new)</option>';
  const { drawings } = await fetchJSON(`/api/drawings/${version}`);
  for (const name of drawings) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    sel.appendChild(opt);
  }
}

function serializeDrawing() {
  const markers = [];
  const lines = [];
  const boxes = [];
  const shapes = [];
  const circles = [];
  const dots = [];
  // Order matters: Leaflet's hierarchy is Rectangle < Polygon < Polyline and
  // Circle < CircleMarker, so the most specific class has to be tested first
  // or a rectangle serializes as a line and a circle as a dot.
  state.drawnItems.eachLayer((layer) => {
    if (layer instanceof L.Rectangle) {
      const b = layer.getBounds();
      boxes.push({ bounds: [[b.getSouth(), b.getWest()], [b.getNorth(), b.getEast()]], color: layer.options.color });
    } else if (layer instanceof L.Polygon) {
      shapes.push({ latlngs: layer.getLatLngs()[0].map((p) => [p.lat, p.lng]), color: layer.options.color });
    } else if (layer instanceof L.Polyline) {
      lines.push({ latlngs: layer.getLatLngs().map((p) => [p.lat, p.lng]), color: layer.options.color });
    } else if (layer instanceof L.Circle) {
      const p = layer.getLatLng();
      circles.push({ lat: p.lat, lng: p.lng, radius: layer.getRadius(), color: layer.options.color });
    } else if (layer instanceof L.CircleMarker) {
      const p = layer.getLatLng();
      dots.push({ lat: p.lat, lng: p.lng, color: layer.options.color, tooltip: layer.options.tooltip });
    } else if (layer instanceof L.Marker) {
      const p = layer.getLatLng();
      markers.push({ lat: p.lat, lng: p.lng, color: layer.options.color || FNGG_YELLOW });
    }
  });
  return { version: state.version, markers, lines, boxes, shapes, circles, dots };
}

function renderDrawing(data) {
  state.drawnItems.clearLayers();
  for (const s of data.shapes || []) {
    L.polygon(s.latlngs, { color: s.color || "#3388ff" }).addTo(state.drawnItems);
  }
  for (const c of data.circles || []) {
    L.circle([c.lat, c.lng], { radius: c.radius, color: c.color || "#3388ff" }).addTo(state.drawnItems);
  }
  for (const d of data.dots || []) {
    const dot = L.circleMarker([d.lat, d.lng], {
      radius: DOT_RADIUS_PX,
      color: d.color || "#3388ff",
      tooltip: d.tooltip,
    }).addTo(state.drawnItems);
    if (d.tooltip) dot.bindTooltip(labelFor(d.tooltip, d.color), LABEL_OPTS);
  }
  for (const m of data.markers || []) {
    L.marker([m.lat, m.lng], { icon: fnggMarkerIcon(m.color), color: m.color || FNGG_YELLOW }).addTo(state.drawnItems);
  }
  for (const l of data.lines || []) {
    L.polyline(l.latlngs, { color: l.color || "#3388ff" }).addTo(state.drawnItems);
  }
  for (const b of data.boxes || []) {
    L.rectangle(b.bounds, { color: b.color || "#3388ff" }).addTo(state.drawnItems);
  }
}

function convertFortniteDrawing(raw) {
  const markers = (raw.marker || []).map((m) => ({ lat: m.latlng[0], lng: m.latlng[1], color: m.color }));
  const lines = (raw.polyline || []).map((p) => ({ latlngs: p.latlng, color: p.color }));
  const boxes = (raw.rectangle || []).map((r) => ({
    bounds: [r.latlng[0], r.latlng[2]],
    color: r.color,
  }));
  // fn.gg also emits polygon/circle/circlemarker; without these the import drops
  // ~70% of a typical drop-spot drawing (and every circlemarker tooltip with it).
  const shapes = (raw.polygon || []).map((p) => ({ latlngs: p.latlng, color: p.color }));
  const circles = (raw.circle || []).map((c) => ({
    lat: c.latlng[0], lng: c.latlng[1], radius: c.radius, color: c.color,
  }));
  const dots = (raw.circlemarker || []).map((c) => ({
    lat: c.latlng[0], lng: c.latlng[1], color: c.color, tooltip: c.tooltip,
  }));
  return { markers, lines, boxes, shapes, circles, dots };
}

const BOOKMARKLET_SRC = `(function(){
  if (!window.Drawing) { alert('No window.Drawing found on this page.'); return; }
  var json = JSON.stringify(window.Drawing);
  navigator.clipboard.writeText(json).then(function(){
    alert('Drawing JSON copied to clipboard (' + json.length + ' chars). Paste it into the local map tool.');
  }, function(){
    prompt('Copy this JSON manually:', json);
  });
})();`;

function wireToolbar() {
  document.getElementById("bookmarklet").href = "javascript:" + encodeURIComponent(BOOKMARKLET_SRC);

  document.getElementById("versionSelect").addEventListener("change", async (e) => {
    state.version = e.target.value;
    setTileLayer(state.version);
    state.drawnItems.clearLayers();
    document.getElementById("drawingName").value = "";
    await loadDrawingList(state.version);
  });

  document.getElementById("drawingSelect").addEventListener("change", async (e) => {
    const name = e.target.value;
    document.getElementById("drawingName").value = name;
    if (!name) {
      state.drawnItems.clearLayers();
      return;
    }
    const data = await fetchJSON(`/api/drawings/${state.version}/${encodeURIComponent(name)}`);
    renderDrawing(data);
  });

  document.getElementById("saveBtn").addEventListener("click", async () => {
    const name = document.getElementById("drawingName").value.trim();
    if (!name) return setStatus("Enter a drawing name first");
    const data = serializeDrawing();
    await fetchJSON(`/api/drawings/${state.version}/${encodeURIComponent(name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    await loadDrawingList(state.version);
    document.getElementById("drawingSelect").value = name;
    setStatus(`Saved "${name}"`);
  });

  document.getElementById("renameBtn").addEventListener("click", async () => {
    const oldName = document.getElementById("drawingSelect").value;
    if (!oldName) return setStatus("Select a saved drawing to rename");
    const newName = prompt("New name:", oldName);
    if (!newName || newName === oldName) return;
    const data = await fetchJSON(`/api/drawings/${state.version}/${encodeURIComponent(oldName)}`);
    await fetchJSON(`/api/drawings/${state.version}/${encodeURIComponent(newName)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    await fetchJSON(`/api/drawings/${state.version}/${encodeURIComponent(oldName)}`, { method: "DELETE" });
    await loadDrawingList(state.version);
    document.getElementById("drawingSelect").value = newName;
    document.getElementById("drawingName").value = newName;
    setStatus(`Renamed to "${newName}"`);
  });

  document.getElementById("deleteBtn").addEventListener("click", async () => {
    const name = document.getElementById("drawingSelect").value;
    if (!name) return setStatus("Select a saved drawing to delete");
    if (!confirm(`Delete "${name}"?`)) return;
    await fetchJSON(`/api/drawings/${state.version}/${encodeURIComponent(name)}`, { method: "DELETE" });
    await loadDrawingList(state.version);
    state.drawnItems.clearLayers();
    document.getElementById("drawingName").value = "";
    setStatus(`Deleted "${name}"`);
  });

  document.getElementById("importBtn").addEventListener("click", () => {
    document.getElementById("importPanel").classList.add("open");
  });
  document.getElementById("importClose").addEventListener("click", () => {
    document.getElementById("importPanel").classList.remove("open");
  });
  document.getElementById("importFetchBtn").addEventListener("click", async () => {
    const url = document.getElementById("importUrl").value.trim();
    if (!url) return setStatus("Enter a fortnite.gg URL first");
    setStatus("Fetching...");
    try {
      const res = await fetch(`/api/import-fgg?url=${encodeURIComponent(url)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Fetch failed");
      document.getElementById("importText").value = JSON.stringify(data.drawing);
      setStatus("Fetched drawing — click Convert & Load");
    } catch (e) {
      setStatus(`Fetch failed: ${e.message}`);
    }
  });
  document.getElementById("importConfirm").addEventListener("click", async () => {
    const raw = document.getElementById("importText").value.trim();
    if (!raw) return setStatus("Paste the drawing JSON first");
    let parsed;
    try { parsed = JSON.parse(raw); } catch { return setStatus("Invalid JSON"); }
    const converted = convertFortniteDrawing(parsed);
    const version = document.getElementById("importVersion").value;
    document.getElementById("versionSelect").value = version;
    state.version = version;
    setTileLayer(version);
    await loadDrawingList(version);
    renderDrawing(converted);
    document.getElementById("importPanel").classList.remove("open");
    setStatus(`Imported drawing onto ${version} (unsaved — click Save to persist)`);
  });

  document.getElementById("migrateBtn").addEventListener("click", () => {
    if (state.drawnItems.getLayers().length === 0) return setStatus("Load a drawing to migrate first");
    state.preMigrateVersion = state.version;
    document.getElementById("migratePanel").classList.add("open");
    document.getElementById("migrateName").value = document.getElementById("drawingName").value;
    setTileLayer(document.getElementById("migrateVersion").value);
    for (const layer of state.drawnItems.getLayers()) {
      if (layer.editing) layer.editing.enable();
      if (layer instanceof L.Marker) layer.dragging.enable();
    }
  });

  document.getElementById("migrateVersion").addEventListener("change", (e) => {
    if (document.getElementById("migratePanel").classList.contains("open")) {
      setTileLayer(e.target.value);
    }
  });

  document.getElementById("migrateClose").addEventListener("click", () => {
    document.getElementById("migratePanel").classList.remove("open");
    if (state.preMigrateVersion) setTileLayer(state.preMigrateVersion);
  });

  document.getElementById("migrateConfirm").addEventListener("click", async () => {
    const targetVersion = document.getElementById("migrateVersion").value;
    const newName = document.getElementById("migrateName").value.trim();
    if (!newName) return setStatus("Enter a name for the migrated drawing");
    const data = serializeDrawing();
    data.version = targetVersion;
    await fetchJSON(`/api/drawings/${targetVersion}/${encodeURIComponent(newName)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    setStatus(`Saved migrated copy "${newName}" on ${targetVersion} (original untouched)`);
    document.getElementById("migratePanel").classList.remove("open");
  });
}

async function main() {
  initMap();
  wireToolbar();
  const versions = await loadVersions();
  if (versions.length === 0) {
    setStatus("No archived versions found in ~/FNGGMapDownloader");
    return;
  }
  state.version = versions[versions.length - 1];
  document.getElementById("versionSelect").value = state.version;
  setTileLayer(state.version);
  await loadDrawingList(state.version);
}

main();

// ── bridge to the app shell ──────────────────────────────────────────────────
// `const state` at the top level of a classic script is a lexical binding, NOT a
// property of window, so the tab switcher in index.html can't see it without
// this. Same for letting the Maps tab refresh the version dropdown after a
// download finishes.
window.state = state;
window.reloadVersionsForMapTab = async function () {
  const versions = await loadVersions();
  if (versions.length && !state.version) {
    state.version = versions[versions.length - 1];
    document.getElementById("versionSelect").value = state.version;
    setTileLayer(state.version);
    await loadDrawingList(state.version);
  }
};

// ── viewport presets (mirrors the Drawings tab / the bot's render sizes) ─────
// The map element is sized in REAL pixels so Leaflet lays out for that viewport,
// then scaled visually to fit the window. invalidateSize() after every change,
// otherwise Leaflet keeps its old dimensions and renders a sliver.
let nativeScreen = [1920, 1080];

async function loadNativeScreen() {
  try {
    const s = await (await fetch('/api/screen')).json();
    if (s.width && s.height) nativeScreen = [s.width, s.height];
  } catch (e) { /* keep default */ }
}

function applyMapViewport() {
  const el = document.getElementById('map');
  const holder = document.getElementById('mapHolder');
  const note = document.getElementById('mapScaleNote');
  const choice = document.getElementById('mapViewport').value;

  if (choice === 'fit') {
    el.classList.remove('fixed');
    el.style.width = '100%';
    el.style.height = '100%';
    el.style.transform = '';
    note.textContent = '';
  } else {
    const [w, h] = choice === 'native' ? nativeScreen : choice.split('x').map(Number);
    const scale = Math.min(holder.clientWidth / w, holder.clientHeight / h, 1);
    el.classList.add('fixed');
    el.style.width = w + 'px';
    el.style.height = h + 'px';
    el.style.transform = `scale(${scale})`;
    note.textContent = `${w}x${h} @ ${Math.round(scale * 100)}%`;
  }
  // Re-frame after resizing. Leaflet keeps centre+zoom across invalidateSize(),
  // so a larger viewport shown scaled-down leaves the drawing as a tiny speck.
  // Re-fitting keeps it readable at every preset, like fn.gg does on load.
  if (state.map) {
    setTimeout(() => {
      state.map.invalidateSize();
      const layers = state.drawnItems && state.drawnItems.getLayers();
      if (layers && layers.length) {
        try {
          state.map.fitBounds(state.drawnItems.getBounds(), { padding: [40, 40] });
          return;
        } catch (e) { /* degenerate bounds — fall through to the whole island */ }
      }
      state.map.fitBounds(WORLD_BOUNDS);
    }, 60);
  }
}

window.applyMapViewport = applyMapViewport;
document.getElementById('mapViewport').addEventListener('change', applyMapViewport);
window.addEventListener('resize', () => {
  if (document.getElementById('mapViewport').value !== 'fit') applyMapViewport();
});
loadNativeScreen();
