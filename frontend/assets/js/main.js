import { $, $$, setStatus, fmt, fmtDate, setupChartDefaults } from './util.js';
import { get } from './api.js';
import * as homeView from './home.js';
import * as mapView from './map.js';
import * as insightsView from './insights.js';
import * as learnView from './learn.js';
import * as reportView from './report.js';

const VIEWS = {
  home: { el: '#view-home', mod: homeView, title: 'Home', focus: '#h-home' },
  map: { el: '#view-map', mod: mapView, title: 'Sightings map', focus: '#h-map' },
  insights: { el: '#view-insights', mod: insightsView, title: 'Insights', focus: '#h-insights' },
  learn: { el: '#view-learn', mod: learnView, title: 'Learn', focus: '#h-learn' },
  report: { el: '#view-report', mod: reportView, title: 'Report a sighting', focus: '#h-report' },
};
let current = null;

// ---------------- themes (Forest, Midnight, Heather), remembered between visits
const THEMES = { forest: '#14513f', midnight: '#0a1512', heather: '#4b3a9a' };
function applyTheme(name, { initial = false } = {}) {
  if (!THEMES[name]) name = 'forest';
  document.documentElement.setAttribute('data-theme', name);
  try { localStorage.setItem('tw-theme', name); } catch { /* private mode: theme just won't persist */ }
  $$('[data-theme-btn]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.themeBtn === name)));
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEMES[name]);
  if (!initial) { setupChartDefaults(); VIEWS[current]?.mod.themeChanged?.(); }
}
$$('[data-theme-btn]').forEach((b) => b.addEventListener('click', () => applyTheme(b.dataset.themeBtn)));

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  const [name = 'home', ...rest] = path.split('/').filter(Boolean);
  return { name: VIEWS[name] ? name : 'home', arg: rest.length ? decodeURIComponent(rest.join('/')) : null, query: new URLSearchParams(query) };
}

async function route() {
  const r = parseHash();
  const v = VIEWS[r.name];
  const changed = current !== r.name;
  for (const [k, def] of Object.entries(VIEWS)) $(def.el).hidden = k !== r.name;
  document.body.dataset.view = r.name;
  $$('[data-nav]').forEach((a) => (a.dataset.nav === r.name ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')));
  document.title = r.name === 'home' ? 'TickWatch UK | Know where ticks are' : `${v.title} | TickWatch UK`;
  current = r.name;
  await v.mod.enter(r);
  if (changed) { window.scrollTo(0, 0); $(v.focus)?.focus({ preventScroll: true }); }
}

async function status() {
  try {
    const h = await get('/health', null, { fresh: true });
    const when = h.last_sync?.finished_at ? fmtDate(h.last_sync.finished_at) : null;
    if (h.status === 'ok') setStatus('ok', `Live data · ${fmt(h.stored_sightings)} sightings${when ? ' · synced ' + when : ''}`);
    else if (h.stored_sightings) setStatus('warn', 'Offline mode · showing saved data');
    else setStatus('warn', 'No data loaded yet');
  } catch { setStatus('warn', 'Server unreachable'); }
}

let saved = null; try { saved = localStorage.getItem('tw-theme'); } catch { /* ignore */ }
applyTheme(saved || 'forest', { initial: true });
setupChartDefaults();
window.addEventListener('hashchange', route);
window.addEventListener('tw:data-changed', status);
status();
if (!location.hash) history.replaceState(null, '', '#/home');
route();
