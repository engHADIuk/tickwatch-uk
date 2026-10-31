// Interactive map view: city bubbles, filters, accessible list alternative and the sighting detail panel.
import { $, $$, h, icon, clear, fmt, fmtDate, fmtDateTime, debounce, toast, riskBadge, riskKey, RISK, skeleton, errorBox, mkChart, destroyCharts, chartBox, C, alpha } from './util.js';
import { get } from './api.js';

const S = { map: null, layer: null, markers: [], filters: {}, selected: null, opts: null, ready: false, charts: {}, mode: 'map', mtoken: 0, dtoken: 0, els: {}, recentDays: 90 };
const UK_BOUNDS = [[50.0, -6.2], [58.8, 1.9]];

const tileUrl = () => `https://{s}.basemaps.cartocdn.com/${document.documentElement.dataset.theme === 'midnight' ? 'dark_all' : 'light_all'}/{z}/{x}/{y}{r}.png`;

/** Called when the colour theme changes: swap the basemap and redraw the open panel's charts. */
export function themeChanged() {
  if (!S.ready) return;
  S.tiles?.setUrl(tileUrl());
  if (S.selected) openCity(S.selected, { fly: false, silent: true });
}

function updateCsv() {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(S.filters)) if (v) u.set(k, v);
  const q = u.toString();
  $('#csv-link').href = `/sightings/export${q ? '?' + q : ''}`;
}

export async function enter({ arg }) {
  if (!S.ready) await init();
  // The map container is hidden while other pages are open; re-measure it before any animation.
  S.map.invalidateSize({ animate: false });
  setTimeout(() => S.map && S.map.invalidateSize(), 60);
  if (arg) openCity(arg, { fly: true, silent: true });
  else if (S.selected) closeDetail({ quiet: true });
}

async function init() {
  S.ready = true;
  try { S.opts = await get('/options'); }
  catch (e) { showError(e); S.opts = { species: [], regions: [], cities: [], date_min: null, date_max: null }; }

  const sp = $('#f-species'), rg = $('#f-region');
  S.opts.species.forEach((s) => sp.append(h('option', { value: s }, s)));
  S.opts.regions.forEach((r) => rg.append(h('option', { value: r }, r)));
  if (S.opts.date_min) { for (const id of ['#f-start', '#f-end']) { $(id).min = S.opts.date_min; $(id).max = S.opts.date_max; } }

  S.map = L.map('map', { zoomSnap: 0.25, zoomDelta: 0.5, minZoom: 4.5, maxZoom: 13, zoomControl: false, worldCopyJump: false,
    maxBounds: [[47.5, -14], [62.5, 6]], maxBoundsViscosity: 0.8 });
  S.map.fitBounds(UK_BOUNDS, { padding: [10, 10], maxZoom: 7 });
  L.control.zoom({ position: 'bottomleft' }).addTo(S.map);
  S.tiles = L.tileLayer(tileUrl(), {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: 'abcd', maxZoom: 13 }).addTo(S.map);
  S.layer = L.layerGroup().addTo(S.map);

  $('#filters').addEventListener('change', onFilterChange);
  $('#f-reset').addEventListener('click', resetFilters);
  $('#empty-reset').addEventListener('click', resetFilters);
  $('#map-retry').addEventListener('click', loadMarkers);
  $('#detail-close').addEventListener('click', () => closeDetail());
  $$('.chip').forEach((c) => c.addEventListener('click', () => applyRange(c.dataset.range)));
  $('#seg-map').addEventListener('click', () => setMode('map'));
  $('#seg-list').addEventListener('click', () => setMode('list'));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#detail').hidden && !$('#view-map').hidden) closeDetail(); });
  await loadMarkers();
}

// ------------------------------------------------------------ filters
function readFilters() {
  S.filters = { start_date: $('#f-start').value, end_date: $('#f-end').value, species: $('#f-species').value, region: $('#f-region').value };
}
function onFilterChange(e) {
  if (e.target.id === 'f-start' || e.target.id === 'f-end') setChip(null);
  readFilters();
  if (S.filters.start_date && S.filters.end_date && S.filters.start_date > S.filters.end_date) {
    toast('The "From" date must be before the "To" date.', 'error'); return;
  }
  loadMarkers();
}
function setChip(range) { $$('.chip').forEach((c) => c.setAttribute('aria-pressed', String(c.dataset.range === range))); }
function applyRange(range) {
  setChip(range);
  const end = S.opts.date_max ? new Date(S.opts.date_max + 'T00:00:00') : new Date();
  if (range === 'all') { $('#f-start').value = ''; $('#f-end').value = ''; S.recentDays = 90; }
  else { const start = new Date(end); start.setDate(start.getDate() - Number(range)); $('#f-start').value = start.toISOString().slice(0, 10); $('#f-end').value = end.toISOString().slice(0, 10); }
  readFilters(); loadMarkers();
}
function resetFilters() { $('#filters').reset(); setChip('all'); readFilters(); loadMarkers(); }

function setMode(mode) {
  S.mode = mode;
  $('#list-view').hidden = mode !== 'list';
  for (const [id, m] of [['#seg-map', 'map'], ['#seg-list', 'list']]) { $(id).classList.toggle('is-active', m === mode); $(id).setAttribute('aria-pressed', String(m === mode)); }
  if (mode === 'map') setTimeout(() => S.map.invalidateSize(), 50);
}

// ------------------------------------------------------------ markers
async function loadMarkers() {
  updateCsv();
  const token = ++S.mtoken;
  $('#map-loading').classList.add('on'); $('#map-error').hidden = true;
  try {
    const data = await get('/map/markers', S.filters);
    if (token !== S.mtoken) return;
    S.markers = data.markers; S.recentDays = data.recent_days;
    renderMarkers(data);
  } catch (e) { if (token === S.mtoken) showError(e); }
  finally { if (token === S.mtoken) $('#map-loading').classList.remove('on'); }
}
function showError(e) { $('#map-error-msg').textContent = e.message; $('#map-error').hidden = false; }

const diameter = (n) => Math.round(Math.min(52, Math.max(30, 24 + Math.sqrt(n) * 2.7)));

/** Relative activity: top third of visible cities = high, middle third = moderate, rest = lower. */
function assignTiers(ms) {
  const order = [...ms].sort((a, b) => b.sightings - a.sightings), third = Math.ceil(order.length / 3);
  order.forEach((m, i) => { m.tier = i < third ? 'high' : i < third * 2 ? 'medium' : 'low'; });
}

function renderMarkers(data) {
  S.layer.clearLayers();
  const ms = data.markers; assignTiers(ms);
  $('#map-empty').hidden = ms.length > 0;
  $('#kpi-total').textContent = fmt(data.total_sightings);
  $('#kpi-cities').textContent = fmt(ms.length);
  $('#kpi-recent-label').textContent = `Final ${data.recent_days} days of data`;
  $('#kpi-recent').textContent = fmt(ms.reduce((a, m) => a + m.recent_sightings, 0));
  $('#kpi-latest').textContent = ms.length ? fmtDate(ms.map((m) => m.last_sighting).sort().pop()) : '–';

  for (const m of ms) {
    const d = diameter(m.sightings), lvl = m.tier;
    const label = `${m.city}: ${m.sightings} sighting${m.sightings === 1 ? '' : 's'}, ${RISK[lvl].label.toLowerCase()}`;
    const icon_ = L.divIcon({ className: 'mk-wrap', iconSize: [d, d], iconAnchor: [d / 2, d / 2],
      html: `<div class="mk mk-${lvl}" style="--d:${d}px">${Number(m.sightings)}</div>` });
    // Larger bubbles sit underneath smaller ones so neighbouring cities never hide each other's counts.
    const mk = L.marker([m.lat, m.lng], { icon: icon_, keyboard: true, title: label, riseOnHover: true, riseOffset: 300000, zIndexOffset: 200000 - m.sightings * 1000 });
    mk.bindTooltip(`${m.city} · ${fmt(m.sightings)}`, { direction: 'top', className: 'tt', offset: [0, -d / 2] });
    mk.on('add', () => {
      const el = mk.getElement(); if (!el) return;
      el.setAttribute('aria-label', label); el.dataset.city = m.city; if (S.selected === m.city) el.classList.add('is-selected');
      // Keyboard users: Enter or Space opens the details, like a button.
      el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openCity(m.city, { fly: true }); } });
    });
    mk.on('click', () => openCity(m.city, { fly: true }));
    mk.addTo(S.layer);
  }
  renderList(ms);
}

function renderList(ms) {
  const body = clear($('#list-body'));
  for (const m of ms) {
    body.append(h('tr', {},
      h('th', { scope: 'row' }, m.city), h('td', {}, m.region), h('td', { class: 'num' }, fmt(m.sightings)),
      h('td', { class: 'num' }, fmt(m.recent_sightings)), h('td', {}, riskBadge(m.tier)),
      h('td', {}, h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: () => { setMode('map'); openCity(m.city, { fly: true }); } }, 'Details', h('span', { class: 'sr-only' }, ` for ${m.city}`)))));
  }
}

function markEl(city) { return $$('.leaflet-marker-icon').find((e) => e.dataset.city === city); }
function highlight(city) { $$('.leaflet-marker-icon.is-selected').forEach((e) => e.classList.remove('is-selected')); if (city) markEl(city)?.classList.add('is-selected'); }

// ------------------------------------------------------------ detail panel
export async function openCity(city, { fly = true, silent = false } = {}) {
  const info = S.markers.find((m) => m.city === city) || (S.opts?.cities || []).find((c) => c.city === city);
  if (!info) { toast(`We do not have a location for "${city}".`, 'error'); return; }
  S.selected = city; highlight(city);
  if (fly) S.map.flyTo([info.lat, info.lng], Math.max(S.map.getZoom(), 7.25), { duration: 0.8 });
  if (!silent) history.replaceState(null, '', `#/map/${encodeURIComponent(city)}`);
  const panel = $('#detail'); panel.hidden = false;
  const body = clear($('#detail-body'));
  body.append(h('div', { class: 'd-head' }, h('h2', { id: 'detail-title', tabindex: '-1' }, city)), skeleton(3, 22), h('div', { style: 'height:12px' }), skeleton(5, 18));
  $('#detail-title').focus({ preventScroll: true });
  const token = ++S.dtoken;
  try { await renderDetail(city, info, token); }
  catch (e) { if (token === S.dtoken) { clear(body).append(h('div', { class: 'd-head' }, h('h2', { id: 'detail-title', tabindex: '-1' }, city)), errorBox(e, () => openCity(city, { fly: false, silent: true }))); } }
}

async function renderDetail(city, info, token) {
  const f = { ...S.filters, location: city };
  const [years, species, season, recent] = await Promise.all([
    get('/reports/trends', { ...f, interval: 'year' }), get('/reports/species', f), get('/reports/seasonality', f),
    get('/sightings', { ...f, limit: 6, sort: 'date_desc' })]);
  if (S.selected !== city || !$('#detail')) return;
  destroyCharts(S.charts);
  const body = clear($('#detail-body'));
  const lvl = riskKey(info.tier || info.risk_level);
  const total = years.total_sightings;
  const lat = info.lat, lng = info.lng;

  body.append(
    h('div', { class: 'd-head' }, riskBadge(lvl),
      h('h2', { id: 'detail-title', tabindex: '-1' }, city),
      h('div', { class: 'where' }, icon('pin'), info.region || '')),
    h('div', { class: 'd-kpis' },
      h('div', {}, h('b', {}, fmt(total)), h('span', {}, 'Sightings')),
      h('div', {}, h('b', {}, fmt(info.recent_sightings ?? 0)), h('span', {}, `Final ${S.recentDays} days of data`)),
      h('div', {}, h('b', {}, info.last_sighting ? fmtDate(info.last_sighting, { month: 'short', year: 'numeric' }) : '–'), h('span', {}, 'Latest'))),
    h('div', { class: 'd-actions' },
      h('a', { class: 'btn btn-primary btn-sm', target: '_blank', rel: 'noopener noreferrer', href: `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}` }, icon('directions'), 'Get directions', h('span', { class: 'sr-only' }, ' (opens Google Maps in a new tab)')),
      h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: () => share(city, total) }, icon('share'), 'Share'),
      h('a', { class: 'btn btn-secondary btn-sm', href: `#/report?city=${encodeURIComponent(city)}` }, icon('plus'), 'Report here')),
    info.explanation ? h('div', { class: 'why' }, h('b', {}, `Recent-activity score: ${Math.round(info.risk_score ?? 0)} / 100`), info.explanation) : null);

  if (total === 0) { body.append(h('p', { class: 'muted' }, 'No sightings in this city match your current filters.')); return; }

  // timeline chart (yearly / monthly toggle)
  const tl = chartBox(`Sightings per year in ${city}`);
  const toggle = h('div', { class: 'seg-sm', role: 'group', 'aria-label': 'Timeline interval' },
    ...['year', 'month'].map((iv) => h('button', { type: 'button', 'aria-pressed': String(iv === 'year'), 'data-iv': iv, onclick: (e) => switchInterval(e, city, tl, iv) }, iv === 'year' ? 'Yearly' : 'Monthly')));
  body.append(h('section', { class: 'd-sec' }, h('h3', {}, 'Activity over time', toggle), tl.box));
  drawTimeline(tl.canvas, years.series, 'year', city);

  // species
  const max = Math.max(...species.species.map((s) => s.sightings), 1);
  body.append(h('section', { class: 'd-sec' }, h('h3', {}, 'Species recorded'),
    h('ul', { class: 'bars' }, species.species.map((s) => h('li', {}, h('span', {}, s.species), h('b', {}, fmt(s.sightings)), h('span', { class: 'bar', 'aria-hidden': 'true' }, h('i', { style: `width:${(s.sightings / max) * 100}%` })))))));

  // seasonality
  const sc = chartBox(`Sightings by month of year in ${city}`, 'short');
  body.append(h('section', { class: 'd-sec' }, h('h3', {}, 'Seasonal pattern', h('span', { class: 'small muted' }, season.peak_month ? `Peak: ${season.peak_month}` : '')), sc.box));
  const peakIdx = season.months.findIndex((m) => m.month === season.peak_month);
  mkChart(S.charts, 'season', sc.canvas, { type: 'bar', data: { labels: season.months.map((m) => m.month), datasets: [{ data: season.months.map((m) => m.sightings), backgroundColor: season.months.map((_, i) => (i === peakIdx ? C().accent : C().primary)), borderRadius: 5 }] },
    options: { scales: { y: { beginAtZero: true, grid: { color: C().grid }, ticks: { precision: 0 } }, x: { grid: { display: false } } } } });

  // recent timeline
  body.append(h('section', { class: 'd-sec' }, h('h3', {}, 'Latest sightings'),
    h('ol', { class: 'timeline' }, recent.items.map((s) => h('li', {},
      h('time', { datetime: s.occurred_at }, fmtDateTime(s.occurred_at)),
      h('span', { class: 'meta' }, s.species || 'Unidentified', s.source === 'user' ? h('span', { class: 'badge badge-info' }, 'Community report') : null),
      s.notes ? h('div', {}, s.notes) : null,
      s.image_url ? h('img', { src: s.image_url, alt: `Photo submitted with the report from ${fmtDate(s.date)}`, loading: 'lazy' }) : null)))));
}

function drawTimeline(canvas, series, interval, city) {
  const peak = series.reduce((a, b) => (b.sightings > a.sightings ? b : a), { sightings: -1, period: '' });
  canvas.setAttribute('aria-label', `${interval === 'year' ? 'Yearly' : 'Monthly'} sightings in ${city}. Highest: ${peak.period} with ${peak.sightings}.`);
  const isYear = interval === 'year';
  mkChart(S.charts, 'timeline', canvas, { type: isYear ? 'bar' : 'line',
    data: { labels: series.map((p) => p.period), datasets: [{ data: series.map((p) => p.sightings), backgroundColor: isYear ? C().primary : alpha(C().primary, 0.15), borderColor: C().primary, borderWidth: isYear ? 0 : 2, borderRadius: 5, fill: !isYear, tension: 0.3, pointRadius: 0 }] },
    options: { scales: { y: { beginAtZero: true, grid: { color: C().grid }, ticks: { precision: 0 } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0 } } } } });
}

async function switchInterval(e, city, tl, iv) {
  $$('button', e.currentTarget.parentElement).forEach((b) => b.setAttribute('aria-pressed', String(b === e.currentTarget)));
  try { const t = await get('/reports/trends', { ...S.filters, location: city, interval: iv }); drawTimeline(tl.canvas, t.series, iv, city); }
  catch (err) { toast(err.message, 'error'); }
}

async function share(city, total) {
  const url = `${location.origin}${location.pathname}#/map/${encodeURIComponent(city)}`;
  if (navigator.share) {
    try { await navigator.share({ title: `Tick sightings in ${city}`, text: `${total} tick sightings recorded in ${city}.`, url }); return; }
    catch (e) { if (e.name === 'AbortError') return; }
  }
  try { await navigator.clipboard.writeText(url); toast('Link copied to clipboard'); }
  catch { window.prompt('Copy this link', url); }
}

function closeDetail({ quiet = false } = {}) {
  const city = S.selected;
  S.selected = null; $('#detail').hidden = true; destroyCharts(S.charts); highlight(null);
  if (!quiet) history.replaceState(null, '', '#/map');
  if (city) markEl(city)?.focus({ preventScroll: true });
}

export const focusCity = openCity;
