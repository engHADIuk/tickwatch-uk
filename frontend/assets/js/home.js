// Home page: a premium landing view with live numbers, a sightings network, a personal "check your area" tool,
// how-it-works, current hotspots, most-recorded species and a call to action. Every block links to something real.
import { $, h, icon, clear, fmt, fmtDate, skeleton, errorBox, countUp, tickArt, C, alpha, mkChart, destroyCharts } from './util.js';
import { get } from './api.js';

let seq = 0;
const charts = {};
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const monthLine = (idx, month, place) => (idx === 0 ? `No sightings have been recorded in ${month} ${place} so far.` : `Historically ${idx}× the average monthly sightings.`);
const TIPS = {
  walking: ['Keep to the middle of paths and avoid brushing long grass.', 'Wear light, long trousers tucked into socks so ticks show up.', 'Check legs, waist and scalp when you get home.'],
  dog: ["Check your dog's ears, neck, chest and between the toes after every walk.", 'Ask your vet which tick treatment suits your dog.', 'Remove any tick promptly with a tick remover.'],
  hiking: ['Use a repellent containing DEET on skin and clothing.', 'Carry a tick remover in your first-aid kit.', 'Do a full body check at the end of the day, including hairline and behind the knees.'],
  gardening: ['Keep grass short and clear leaf litter near borders.', 'Wear gloves and long sleeves when clearing undergrowth.', 'Shower and check yourself afterwards.'],
};
const ACTIVITIES = [['walking', 'Walking'], ['dog', 'Dog walking'], ['hiking', 'Hiking'], ['gardening', 'Gardening']];

export const themeChanged = () => enter();

export async function enter() {
  const root = $('#home-body'), my = ++seq;
  if (!root.firstChild) root.append(h('div', { style: 'padding:90px 28px;max-width:1240px;margin:0 auto' }, skeleton(4, 28)));
  try {
    const [markers, species, risk, dq, season, years] = await Promise.all([
      get('/map/markers'), get('/reports/species'), get('/insights/risk', { limit: 3 }), get('/data-quality'), get('/reports/seasonality'), get('/reports/trends', { interval: 'year' })]);
    if (my !== seq) return;
    destroyCharts(charts); clear(root); render(root, { markers, species, risk, dq, season, years });
  } catch (e) { if (my === seq) clear(root).append(h('div', { class: 'home-wrap', style: 'padding-top:40px' }, errorBox(e, enter))); }
}

function render(root, d) {
  const ms = d.markers.markers, total = d.dq.stored_sightings;
  const regions = new Set(ms.map((m) => m.region)).size;

  // ---------------- hero
  root.append(h('section', { class: 'hero' }, h('div', { class: 'hero-inner' },
    h('div', { class: 'hero-copy' },
      h('span', { class: 'pill-hero' }, h('b', {}, 'LIVE'), `${fmt(total)} sightings across ${ms.length} UK cities`),
      h('h1', { id: 'h-home', tabindex: '-1' }, 'Know where ticks are. ', h('em', {}, 'Protect'), ' the ones you love.'),
      h('p', { class: 'sub' }, 'TickWatch UK maps tick sightings, shows when activity peaks near you, and lets anyone report a sighting in under a minute.'),
      h('div', { class: 'hero-cta' },
        h('a', { class: 'btn btn-light btn-lg', href: '#/map' }, icon('map'), 'Explore the map'),
        h('a', { class: 'btn btn-outline-light btn-lg', href: '#/report' }, icon('plus'), 'Report a sighting')),
      h('div', { class: 'trust' },
        h('span', {}, icon('check'), 'Cleaned, de-duplicated open data'), h('span', {}, icon('check'), 'Explainable activity scores'), h('span', {}, icon('check'), 'Accessible and keyboard friendly'))),
    h('div', { class: 'hero-viz' },
      h('div', { class: 'vtitle' }, h('span', {}, 'Sightings network'), h('a', { href: '#/map' }, 'Open map', icon('directions'))),
      constellation(ms)))));

  // ---------------- floating cards: check your area + live numbers
  const wrap = h('div', { class: 'home-wrap' });
  root.append(wrap);
  wrap.append(h('div', { class: 'floaty' }, checkCard(ms), liveCard(d, total, ms.length, regions)));

  // ---------------- this month
  const m = new Date().getMonth(), cur = d.season.months[m];
  const idx = cur.seasonal_index ?? 0, peak = d.season.peak_month;
  wrap.append(h('div', { class: 'season-banner', style: 'margin-top:22px', role: 'note' },
    h('div', { class: 'ic' }, icon('calendar')),
    h('div', {}, h('b', {}, `${MONTHS[m]} in the UK: ${idx >= 1.2 ? 'a busy time for ticks' : idx >= 0.7 ? 'typical tick activity' : 'quieter, but stay alert'}`),
      h('p', {}, `${idx === 0 ? `No sightings have been recorded in ${MONTHS[m]}` : `${MONTHS[m]} has historically seen ${idx}× the average monthly sightings`}. The busiest month is ${peak}. Ticks can still be active on mild days, so keep checking.`)),
    h('a', { class: 'btn btn-secondary btn-sm', style: 'margin-left:auto', href: '#/learn' }, 'See seasonal charts')));

  // ---------------- how it works
  wrap.append(h('section', { class: 'home-sec' }, h('h2', { class: 'big' }, 'From sighting to safer outdoors'),
    h('p', { class: 'intro' }, 'Three simple ways to use TickWatch UK, whether you walk a dog, run a surgery or just love being outside.'),
    h('div', { class: 'grid g3 how' },
      step('1', 'map', 'Explore', 'See where ticks are being recorded. Filter by date and species, then open any city for its timeline, species mix and latest sightings.', '#/map', 'Open the map'),
      step('2', 'book', 'Learn', 'Identify common ticks, see when they peak near you and learn how to prevent bites and remove a tick safely.', '#/learn', 'Start learning'),
      step('3', 'camera', 'Report', 'Add your own sighting with a photo. Each report is validated, checked for duplicates and appears on the map straight away.', '#/report', 'Report a sighting'))));

  // ---------------- hotspots + species
  const top = Math.max(...d.species.species.map((s) => s.sightings), 1);
  wrap.append(h('section', { class: 'home-sec' }, h('div', { class: 'grid g2' },
    h('div', { class: 'card' }, h('h2', {}, 'Highest recent activity'), h('p', { class: 'sub' }, `Explainable score as of ${fmtDate(d.risk.as_of)} (the latest sighting in the data).`),
      d.risk.cities.map((c, i) => h('a', { class: 'hot-row', href: `#/map/${encodeURIComponent(c.city)}` },
        h('span', { class: 'rk' }, i + 1), h('span', {}, h('div', { class: 'nm' }, c.city), h('div', { class: 'rg' }, c.region)), h('span', { class: 'sc', 'aria-label': `score ${Math.round(c.risk_score)} out of 100` }, Math.round(c.risk_score)))),
      h('a', { class: 'btn btn-ghost btn-sm', style: 'margin-top:10px', href: '#/insights' }, 'See the full ranking')),
    h('div', { class: 'card' }, h('h2', {}, 'Most recorded species'), h('p', { class: 'sub' }, 'The ticks people encounter most often.'),
      d.species.species.slice(0, 4).map((s, i) => h('div', { class: 'species-row' },
        h('span', { class: 'art' }, tickArt(C().palette[i % C().palette.length])), h('span', {}, h('b', {}, s.species), h('div', { class: 'small muted' }, s.latin_name)), h('b', {}, fmt(s.sightings)),
        h('span', { class: 'bar', 'aria-hidden': 'true' }, h('i', { style: `width:${(s.sightings / top) * 100}%` })))),
      h('a', { class: 'btn btn-ghost btn-sm', style: 'margin-top:10px', href: '#/learn' }, 'Open the species guide')))));

  // ---------------- call to action
  wrap.append(h('section', { class: 'cta-band' },
    h('div', {}, h('h2', {}, 'Seen a tick? Tell us in under a minute.'), h('p', {}, 'Every report helps other owners, walkers and vets see where ticks are active. No account needed, and we never ask for your name or address.')),
    h('div', { class: 'hero-cta' }, h('a', { class: 'btn btn-light btn-lg', href: '#/report' }, icon('plus'), 'Report a sighting'), h('a', { class: 'btn btn-outline-light btn-lg', href: '#/learn' }, 'How to remove a tick'))));
}

function step(n, ic, title, text, href, cta) {
  return h('div', { class: 'card lift' }, h('span', { class: 'num-b', 'aria-hidden': 'true' }, n), h('div', { class: 'ic' }, icon(ic)), h('h3', {}, title), h('p', {}, text),
    h('a', { class: 'btn btn-ghost btn-sm', style: 'margin-top:12px;padding-left:0', href }, cta, icon('directions')));
}

// ---------------- hero visual: cities as a glowing network (real data, real positions)
function constellation(ms) {
  const NS = 'http://www.w3.org/2000/svg', W = 460, H = 600;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('class', 'constellation'); svg.setAttribute('role', 'group'); svg.setAttribute('aria-label', 'Network of UK cities with tick sightings. Each point links to that city on the map.');
  if (!ms.length) return svg;
  const cx = Math.cos((54 * Math.PI) / 180);
  const raw = ms.map((m) => ({ ...m, rx: m.lng * cx, ry: -m.lat }));
  const minX = Math.min(...raw.map((p) => p.rx)), maxX = Math.max(...raw.map((p) => p.rx));
  const minY = Math.min(...raw.map((p) => p.ry)), maxY = Math.max(...raw.map((p) => p.ry));
  const padL = 70, padR = 150, padV = 60;
  const sc = Math.min((W - padL - padR) / Math.max(maxX - minX, 0.01), (H - 2 * padV) / Math.max(maxY - minY, 0.01));
  const offX = padL + (W - padL - padR - (maxX - minX) * sc) / 2, offY = padV + (H - 2 * padV - (maxY - minY) * sc) / 2;
  const pts = raw.map((p) => ({ ...p, x: offX + (p.rx - minX) * sc, y: offY + (p.ry - minY) * sc }));
  const maxN = Math.max(...pts.map((p) => p.sightings), 1);
  const seen = new Set();
  for (const a of pts) {
    pts.filter((b) => b !== a).map((b) => ({ b, d: Math.hypot(a.x - b.x, a.y - b.y) })).sort((p, q) => p.d - q.d).slice(0, 2).forEach(({ b }) => {
      const key = [a.city, b.city].sort().join('|'); if (seen.has(key)) return; seen.add(key);
      const l = document.createElementNS(NS, 'line'); l.setAttribute('class', 'link'); l.setAttribute('x1', a.x); l.setAttribute('y1', a.y); l.setAttribute('x2', b.x); l.setAttribute('y2', b.y); svg.append(l);
    });
  }
  const topThree = new Set([...pts].sort((a, b) => b.sightings - a.sightings).slice(0, 2).map((p) => p.city));
  pts.forEach((p, i) => {
    const r = 4 + Math.sqrt(p.sightings / maxN) * 7;
    const g = document.createElementNS(NS, 'g'); g.setAttribute('class', 'node'); g.setAttribute('tabindex', '0'); g.setAttribute('role', 'link');
    g.setAttribute('aria-label', `${p.city}, ${p.sightings} sightings. Open on the map.`);
    g.innerHTML = `<circle class="halo pulse" cx="${p.x}" cy="${p.y}" r="${r * 1.7}" style="animation-delay:${(i % 7) * 0.45}s"></circle><circle class="core" cx="${p.x}" cy="${p.y}" r="${r}"></circle>`;
    const t = document.createElementNS(NS, 'text'); t.setAttribute('x', p.x + r + 6); t.setAttribute('y', p.y + 4); t.textContent = `${p.city} · ${p.sightings}`;
    if (topThree.has(p.city)) t.style.opacity = '1';
    g.append(t);
    const go = () => { location.hash = `#/map/${encodeURIComponent(p.city)}`; };
    g.addEventListener('click', go); g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    svg.append(g);
  });
  return svg;
}

// ---------------- "Check your area": a small tool with a clear purpose
function liveCard(d, total, cities, regions) {
  const spark = { box: h('div', { class: 'chart-box short' }, h('canvas', { role: 'img', 'aria-label': `Sightings per year from ${d.years.series[0]?.period} to ${d.years.series.at(-1)?.period}. Busiest year ${d.years.peak?.period} with ${d.years.peak?.sightings}.` })) };
  queueMicrotask(() => mkChart(charts, 'spark', spark.box.firstChild, { type: 'bar', data: { labels: d.years.series.map((p) => p.period), datasets: [{ data: d.years.series.map((p) => p.sightings), backgroundColor: alpha(C().primary, 0.85), borderRadius: 4 }] }, options: { scales: { y: { beginAtZero: true, grid: { color: C().grid }, ticks: { precision: 0, maxTicksLimit: 4 } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 6, maxRotation: 0 } } } } }));
  const nums = [[total, 'Sightings recorded'], [cities, 'Cities covered'], [regions, 'UK regions'], [d.dq.community_reports, 'Community reports']];
  const els = nums.map(([n, label]) => { const b = h('b', {}, '0'); countUp(b, n); return h('div', {}, b, h('span', {}, label)); });
  return h('div', { class: 'card live-card' }, h('h2', {}, 'The data at a glance'), h('p', { class: 'sub', style: 'margin:0' }, `${fmtDate(d.dq.date_range.from)} to ${fmtDate(d.dq.date_range.to)}`),
    h('div', { class: 'livestats' }, els),
    h('div', { style: 'margin-top:14px' }, h('b', { style: 'font-size:.86rem' }, 'Sightings per year'), spark.box),
    h('p', { class: 'small muted', style: 'margin:8px 0 0' }, 'Every record is validated and de-duplicated before it reaches the map.'), h('a', { class: 'btn btn-ghost btn-sm', style: 'align-self:flex-start', href: '#/insights' }, 'Explore the insights'));
}

function checkCard(ms) {
  const cities = [...ms].sort((a, b) => a.city.localeCompare(b.city));
  const sel = h('select', { id: 'chk-city' }, cities.map((c) => h('option', { value: c.city }, `${c.city} (${c.region})`)));
  const result = h('div', { class: 'check-result', 'aria-live': 'polite' }, skeleton(2, 18));
  let activity = 'walking';
  const chips = h('div', { class: 'chips', role: 'group', 'aria-label': 'What are you planning?' }, ACTIVITIES.map(([k, label]) =>
    h('button', { type: 'button', class: 'chip', 'aria-pressed': String(k === activity), onclick: (e) => { activity = k; [...chips.children].forEach((b) => b.setAttribute('aria-pressed', String(b === e.currentTarget))); run(); } }, label)));
  async function run() {
    const city = sel.value;
    try {
      const s = await get('/reports/seasonality', { location: city });
      const m = new Date().getMonth(), idx = s.months[m].seasonal_index ?? 0;
      const lvl = idx >= 1.3 ? ['high', 'Busier than usual'] : idx >= 0.7 ? ['medium', 'Typical activity'] : ['low', 'Quieter than usual'];
      const pos = Math.max(2, Math.min(98, (idx / 2) * 100));
      clear(result).append(
        h('div', { class: 'level' }, h('span', { class: `badge badge-${lvl[0]}` }, lvl[1]), h('span', { class: 'big' }, `${MONTHS[m]} in ${city}`)),
        h('div', { class: 'meter-bar', role: 'img', 'aria-label': `${idx} times the average month` }, h('i', { style: `left:${pos}%` })),
        h('p', { class: 'small muted', style: 'margin:6px 0 0' }, `${monthLine(idx, MONTHS[m], 'here')} Peak season: ${s.peak_month}.`),
        h('ul', {}, TIPS[activity].map((t) => h('li', {}, t))),
        h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;margin-top:12px' },
          h('a', { class: 'btn btn-primary btn-sm', href: `#/map/${encodeURIComponent(city)}` }, icon('pin'), `See ${city} on the map`), h('a', { class: 'btn btn-secondary btn-sm', href: '#/learn' }, 'Tick-check guide')),
        h('p', { class: 'small muted', style: 'margin:10px 0 0' }, 'Based on past sighting counts, not a forecast. Ticks can be active whenever it is mild.'));
    } catch (e) { clear(result).append(errorBox(e, run)); }
  }
  sel.addEventListener('change', run);
  const preset = cities.find((c) => c.city === 'Nottingham') || cities[0];
  if (preset) sel.value = preset.city;
  run();
  return h('div', { class: 'card check-card' }, h('h2', {}, 'Check your area'), h('p', { class: 'muted', style: 'margin:4px 0 0' }, 'Pick a city and what you are planning. Get this month\'s tick activity and practical tips.'),
    h('div', { class: 'controls' }, h('label', { class: 'field' }, h('span', {}, 'City'), sel), h('div', { class: 'field' }, h('span', {}, 'I am planning to go…'), chips)), result);
}
