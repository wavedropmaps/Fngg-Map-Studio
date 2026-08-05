/* Maps tab — download versions, scan for new ones, inspect the archive.
   Replaces the standalone Kotlin GUI. Long jobs run server-side and are polled
   via /api/job/<id> rather than held open on one request. */

(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  let pollTimer = null;
  let activeJob = null;
  const selected = new Set();   // versions queued for download
  let queueAborted = false;

  function fmtBytes(n) {
    if (!n) return '—';
    const u = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return n.toFixed(i === 0 ? 0 : 1) + ' ' + u[i];
  }

  function setProgress(done, total, note) {
    $('progressWrap').classList.add('on');
    const pct = total ? Math.round((done / total) * 100) : 0;
    $('progressBar').style.width = pct + '%';
    $('progressText').textContent = total
      ? `${done.toLocaleString()} / ${total.toLocaleString()} tiles (${pct}%) ${note || ''}`
      : (note || 'working…');
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    activeJob = null;
    $('dlBtn').disabled = false;
    $('scanBtn').disabled = false;
    $('dlCancel').disabled = true;
  }

  /* The bar used to sit at 100% forever once a job finished, which reads as
     "still working". Clear it back to idle, but leave the text so you can still
     see what happened. */
  function resetProgressBar() {
    $('progressBar').style.width = '0%';
  }

  // Promise-based so a queue of downloads can await each one in turn.
  // Each poll gets its OWN interval handle rather than sharing one module-level
  // slot: starting a second job used to clearInterval the first, whose promise
  // then never settled, so a running download queue silently stalled forever.
  function pollJob(id, onDone) {
    activeJob = id;
    return new Promise((resolve) => {
      let timer = null;
      let misses = 0;
      const finish = (j) => { clearInterval(timer); if (pollTimer === timer) pollTimer = null; resolve(j); };
      timer = setInterval(async () => {
        let j;
        try {
          j = await (await fetch('/api/job/' + id)).json();
        } catch (e) { return; }      // transient; next tick retries

        // An unknown job id returns {error} with NO state — e.g. after a server
        // restart. Without this the tab polls forever and the buttons stay dead.
        if (j.error && !j.state) {
          if (++misses >= 5) {
            stopPolling();
            resetProgressBar();
            $('progressText').textContent = 'Lost track of that job (did the server restart?).';
            return finish({ state: 'error', error: j.error });
          }
          return;
        }
        misses = 0;

        setProgress(j.done || 0, j.total || 0, j.note || '');
        if (j.kind === 'scan' && j.found && j.found.length) {
          $('scanFound').textContent = 'found: ' + j.found.join(', ');
        }
        if (j.state === 'running') return;

        stopPolling();
        resetProgressBar();
        if (j.state === 'error') {
          $('progressText').textContent = 'Failed: ' + (j.error || 'unknown error');
        } else if (j.state === 'cancelled') {
          $('progressText').textContent = 'Cancelled. Re-running skips whatever already downloaded.';
        } else {
          onDone && onDone(j);
        }
        refreshVersionTable();
        finish(j);
      }, 700);
      pollTimer = timer;
    });
  }

  async function refreshVersionTable() {
    const body = $('versionRows');
    let data;
    try {
      data = await (await fetch('/api/versions/detail')).json();
    } catch (e) {
      body.innerHTML = '<tr><td colspan="6" style="color:#e07d7d">Server unreachable</td></tr>';
      return;
    }
    const vs = data.versions || [];
    if (!vs.length) {
      body.innerHTML = '<tr><td colspan="6" style="color:#777">Nothing downloaded yet — grab a version above.</td></tr>';
      return;
    }
    body.innerHTML = '';
    for (const v of vs) {
      const tr = document.createElement('tr');
      const pill = (ok) => `<span class="pill ${ok ? 'yes' : 'no'}">${ok ? 'yes' : 'no'}</span>`;
      tr.innerHTML =
        `<td><strong>${v.version}</strong></td>` +
        `<td>${(v.tiles || 0).toLocaleString()}</td>` +
        `<td>${fmtBytes(v.bytes)}</td>` +
        `<td>${pill(v.has_pyramid)}</td>` +
        `<td>${pill(v.has_final_image)}</td>` +
        `<td></td>`;
      const cell = tr.lastElementChild;

      const openFolder = document.createElement('button');
      openFolder.className = 'btn';
      openFolder.textContent = 'Open folder';
      openFolder.onclick = () => fetch('/api/open', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version: v.version, what: 'folder' }),
      });
      cell.appendChild(openFolder);

      if (v.has_final_image) {
        const openImg = document.createElement('button');
        openImg.className = 'btn';
        openImg.style.marginLeft = '6px';
        openImg.textContent = 'Open HQ map';
        openImg.onclick = () => fetch('/api/open', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ version: v.version, what: 'final' }),
        });
        cell.appendChild(openImg);
      } else {
        const stitch = document.createElement('button');
        stitch.className = 'btn';
        stitch.style.marginLeft = '6px';
        stitch.textContent = 'Stitch big image';
        stitch.onclick = async () => {
          stitch.disabled = true;
          setProgress(0, 0, `stitching ${v.version}…`);
          const r = await (await fetch('/api/stitch', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ version: v.version }),
          })).json();
          if (!r.job) { stitch.disabled = false; return; }
          // Cancel was dead here before: the button stayed disabled because only
          // the download path ever enabled it, so a long stitch couldn't be stopped.
          $('dlCancel').disabled = false;
          const j = await pollJob(r.job, () => {
            $('progressText').textContent = `Stitched ${v.version}.`;
          });
          stitch.disabled = false;
          if (j.state === 'cancelled') $('progressText').textContent = `Stitch of ${v.version} cancelled.`;
        };
        cell.appendChild(stitch);
      }
      body.appendChild(tr);
    }
  }
  window.refreshVersionTable = refreshVersionTable;

  // The old Kotlin GUI showed a thumbnail of the island next to each version,
  // which is the only way to tell them apart — "38.01" means nothing on its own.
  // Thumbnails are each map's zoom-0 tile: the whole island in one 256px image.
  let knownVersions = [];

  async function loadKnownVersions() {
    const grid = $('versionGrid');
    try {
      const data = await (await fetch('/api/known-versions')).json();
      knownVersions = data.versions || [];
    } catch (e) {
      grid.innerHTML = '<div style="color:#e07d7d;font-size:13px">Could not load version list</div>';
      return;
    }
    renderVersionGrid();
  }
  window.loadKnownVersions = loadKnownVersions;

  function renderVersionGrid() {
    const grid = $('versionGrid');
    const filter = $('dlFilter').value.trim().toLowerCase();
    const onlyMine = $('dlOnlyMine').checked;
    const chosen = $('dlVersion').value.trim();

    // Newest first — almost always what you want.
    let vs = knownVersions.slice().reverse();
    if (filter) vs = vs.filter((v) => v.version.toLowerCase().includes(filter));
    if (onlyMine) vs = vs.filter((v) => v.downloaded);

    if (!vs.length) {
      grid.innerHTML = '<div style="color:#777;font-size:13px">No versions match that filter.</div>';
      return;
    }

    grid.innerHTML = '';
    for (const v of vs) {
      const card = document.createElement('div');
      card.className = 'vcard' + (v.downloaded ? ' have' : '') + (v.version === chosen ? ' sel' : '');
      card.title = v.downloaded ? `${v.version} — already downloaded` : `${v.version} — click to select`;

      const img = document.createElement('img');
      // loading="lazy" matters: un-downloaded versions have their thumbnail
      // fetched from fn.gg on demand, so eager-loading 100+ would hammer them.
      img.loading = 'lazy';
      img.alt = v.version;
      img.src = '/api/preview/' + v.version;
      img.onerror = () => { img.style.visibility = 'hidden'; };
      card.appendChild(img);

      const label = document.createElement('div');
      label.className = 'vlabel';
      label.textContent = v.version;
      card.appendChild(label);

      if (v.downloaded) {
        const tick = document.createElement('div');
        tick.className = 'vtick';
        tick.textContent = '✓';
        card.appendChild(tick);
      }

      // Multi-select: clicking toggles, so several maps can be queued at once.
      card.onclick = () => {
        if (selected.has(v.version)) selected.delete(v.version);
        else selected.add(v.version);
        card.classList.toggle('sel', selected.has(v.version));
        updateSelectionUI();
      };
      grid.appendChild(card);
    }
    updateSelectionUI();
  }

  function updateSelectionUI() {
    const n = selected.size;
    $('selCount').textContent = n
      ? `${n} selected: ${[...selected].join(', ')}`
      : 'None selected — click map thumbnails to queue them.';
    $('dlClear').style.display = n ? '' : 'none';
    $('dlBtn').textContent = n > 1 ? `Download ${n} maps` : 'Download';
  }

  $('dlFilter').addEventListener('input', renderVersionGrid);
  $('dlOnlyMine').addEventListener('change', renderVersionGrid);

  $('dlBtn').addEventListener('click', async () => {
    // Typed version wins if present; otherwise download everything selected.
    const typed = $('dlVersion').value.trim();
    const queue = typed ? [typed] : [...selected];
    if (!queue.length) {
      $('progressWrap').classList.add('on');
      $('progressText').textContent = 'Pick at least one map (click a thumbnail) or type a version.';
      return;
    }

    queueAborted = false;
    $('dlBtn').disabled = true;
    $('dlCancel').disabled = false;
    const stitch = $('dlStitch').checked;
    const summary = [];

    for (let i = 0; i < queue.length; i++) {
      if (queueAborted) break;
      const version = queue[i];
      const pos = queue.length > 1 ? `[map ${i + 1} of ${queue.length}] ` : '';
      setProgress(0, 0, `${pos}${version}: detecting tile scheme…`);

      let r;
      try {
        r = await (await fetch('/api/download', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ version, stitch }),
        })).json();
      } catch (e) {
        summary.push(`${version}: request failed`);
        continue;
      }
      if (r.error) { summary.push(`${version}: ${r.error}`); continue; }

      const j = await pollJob(r.job, () => {});
      const res = j.result || {};
      if (j.state === 'cancelled') { summary.push(`${version}: cancelled`); break; }
      if (j.state === 'error') { summary.push(`${version}: ${j.error}`); continue; }
      summary.push(`${version}: ${res.ok || 0} new, ${res.skip || 0} existing, ${res.fail || 0} failed`);
      selected.delete(version);
    }

    stopPolling();
    resetProgressBar();
    $('progressText').textContent = summary.join('  •  ') || 'Nothing downloaded.';
    loadKnownVersions();
    if (window.reloadVersionsForMapTab) window.reloadVersionsForMapTab();
  });

  // Cancels whatever job is live -- download OR stitch -- and drops the rest of
  // the queue, so one click stops everything rather than just the current map.
  $('dlCancel').addEventListener('click', () => {
    queueAborted = true;
    if (activeJob) fetch('/api/job/' + activeJob + '/cancel', { method: 'POST' });
    $('progressText').textContent = 'Cancelling…';
  });

  $('dlClear').addEventListener('click', () => {
    selected.clear();
    renderVersionGrid();
  });

  $('scanBtn').addEventListener('click', async () => {
    $('scanBtn').disabled = true;
    $('scanFound').textContent = '';
    setProgress(0, 0, 'starting scan…');
    const r = await (await fetch('/api/scan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    })).json();
    pollJob(r.job, (j) => {
      const found = (j.result && j.result.found) || [];
      $('progressText').textContent = found.length
        ? `Scan finished — ${found.length} version(s) found.`
        : 'Scan finished — nothing newer found.';
      $('scanFound').textContent = found.length ? 'found: ' + found.join(', ') : '';
      if (found.length) loadKnownVersions();
    });
  });

  refreshVersionTable();
  loadKnownVersions();
})();
