// Small DOM + formatting helpers shared by every view. No framework: plain, safe DOM building.
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Build an element. Text is always inserted as text nodes, never as HTML (prevents XSS from user notes). */
export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export function icon(name, cls = 'i') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', cls); svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#i-${name}`); svg.append(use);
  return svg;
}

export const fmt = (n) => new Intl.NumberFormat('en-GB').format(n ?? 0);
export function fmtDate(iso, opts = { day: 'numeric', month: 'short', year: 'numeric' }) {
  if (!iso) return '–';
  const d = new Date(iso.length === 10 ? iso + 'T00:00:00' : iso);
  return Number.isNaN(+d) ? '–' : d.toLocaleDateString('en-GB', opts);
}
export const fmtDateTime = (iso) => fmtDate(iso, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
export const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
export const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

export const RISK = {
  low: { label: 'Lower activity', badge: 'badge-low' },
  medium: { label: 'Moderate activity', badge: 'badge-medium' },
  high: { label: 'Higher activity', badge: 'badge-high' },
};
export const riskKey = (k) => (RISK[k] ? k : 'low');
export const riskBadge = (k) => h('span', { class: `badge ${RISK[riskKey(k)].badge}` }, RISK[riskKey(k)].label);

export function toast(message, kind = 'info') {
  const box = $('#toasts');
  const t = h('div', { class: `toast ${kind === 'error' ? 'error' : ''}`, role: kind === 'error' ? 'alert' : 'status' }, icon(kind === 'error' ? 'alert' : 'check'), message);
  box.append(t);
  setTimeout(() => t.remove(), 4200);
}

export function skeleton(lines = 3, height = 16) {
  return h('div', { 'aria-hidden': 'true', style: 'display:grid;gap:10px' },
    Array.from({ length: lines }, (_, i) => h('div', { class: 'skeleton', style: `height:${height}px;width:${i === lines - 1 ? 60 : 100}%` })));
}

export function errorBox(err, retry) {
  return h('div', { class: 'err-box', role: 'alert' }, err?.message || 'Something went wrong.',
    retry ? h('div', {}, h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: retry }, 'Try again')) : null);
}

// ---------- charts ----------
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
/** Chart colours come from the active theme's CSS variables, so every chart follows the theme. */
export const C = () => ({ primary: css('--chart-1'), accent: css('--chart-2'), grid: css('--grid'), soft: css('--primary-soft'),
  text: css('--muted'), surface: css('--surface'), palette: [1, 2, 3, 4, 5, 6, 7].map((i) => css(`--chart-${i}`)) });
export const alpha = (hex, a) => { const n = parseInt(hex.replace('#', ''), 16); return `rgba(${n >> 16 & 255}, ${n >> 8 & 255}, ${n & 255}, ${a})`; };

export function countUp(el, target, ms = 900) {
  const final = Number(target) || 0;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || final < 2) { el.textContent = fmt(final); return; }
  const t0 = performance.now();
  const tick = (now) => { const k = Math.min(1, (now - t0) / ms), e = 1 - (1 - k) ** 3; el.textContent = fmt(Math.round(final * e)); if (k < 1) requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
}

export function setupChartDefaults() {
  if (!window.Chart) return;
  const C = window.Chart;
  C.defaults.font.family = getComputedStyle(document.body).fontFamily;
  C.defaults.font.size = 12; C.defaults.color = css('--muted') || '#5d6f69';
  C.defaults.plugins.legend.display = false;
  C.defaults.plugins.tooltip.backgroundColor = css('--primary-strong') === css('--primary') ? '#12302a' : (document.documentElement.dataset.theme === 'midnight' ? '#050e0b' : '#12302a');
  C.defaults.plugins.tooltip.padding = 10; C.defaults.plugins.tooltip.cornerRadius = 10;
  C.defaults.plugins.tooltip.titleFont = { weight: '700' };
  C.defaults.animation.duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 500;
}

/** Create (or replace) a chart on a canvas, keeping a registry so we can destroy it later. */
export function mkChart(registry, key, canvas, config) {
  if (registry[key]) registry[key].destroy();
  registry[key] = new window.Chart(canvas, { ...config, options: { responsive: true, maintainAspectRatio: false, ...(config.options || {}) } });
  return registry[key];
}
export const destroyCharts = (registry) => { for (const k of Object.keys(registry)) { registry[k].destroy(); delete registry[k]; } };

export function chartBox(label, cls = '') {
  const canvas = h('canvas', { role: 'img', 'aria-label': label });
  return { box: h('div', { class: `chart-box ${cls}` }, canvas), canvas };
}

// Stylised tick artwork (illustration, not a photograph)
export function tickArt(color = '#14513f') {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', '0 0 48 48'); svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = `<g stroke="${color}" stroke-width="2.2" stroke-linecap="round" fill="none"><path d="M14 18 6 13M13 24 5 24M14 30 7 36M34 18l8-5M35 24l8 0M34 30l7 6"/></g><ellipse cx="24" cy="28" rx="10" ry="12" fill="${color}"/><circle cx="24" cy="12.500" r="4.500" fill="${color}"/><ellipse cx="21" cy="25" rx="3" ry="4.500" fill="#fff" opacity=".18"/>`;
  return svg;
}

export function haversineKm(a, b) {
  const R = 6371, rad = (x) => (x * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat), dLng = rad(b.lng - a.lng);
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

export function setStatus(kind, text) {
  const pill = $('#status-pill');
  pill.className = `pill ${kind === 'ok' ? 'pill-ok' : kind === 'warn' ? 'pill-warn' : 'pill-muted'}`;
  $('#status-text').textContent = text;
}
