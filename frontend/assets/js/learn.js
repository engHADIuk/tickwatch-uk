// Learn view: species identification guide, prevention tips, removal steps and a seasonal activity chart for any city.
import { $, h, icon, clear, fmt, skeleton, errorBox, mkChart, destroyCharts, chartBox, tickArt, C, alpha } from './util.js';
import { get } from './api.js';

const charts = {};
let seq = 0;

export function themeChanged() { $('#learn-body').dataset.ready = ''; return enter(); }

export async function enter() {
  const root = $('#learn-body');
  if (root.dataset.ready === '1') return;
  clear(root).append(h('div', { class: 'grid g3' }, [1, 2, 3].map(() => h('div', { class: 'card' }, skeleton(5, 16)))));
  const my = ++seq;
  try {
    const [edu, cities] = await Promise.all([get('/education'), get('/reports/regions', { group_by: 'city' })]);
    if (my !== seq) return;
    clear(root); render(root, edu, cities.groups); root.dataset.ready = '1';
  } catch (e) { clear(root).append(errorBox(e, () => { root.dataset.ready = ''; enter(); })); }
}

function render(root, edu, cityGroups) {
  // size guide
  root.append(h('section', { class: 'card' }, h('h2', {}, 'How big is a tick?'), h('p', { class: 'sub' }, 'Ticks are easy to miss. Approximate sizes, not to scale.'),
    h('div', { class: 'sizes' }, [['Larva', 5, 'under 1 mm'], ['Nymph', 9, 'about 1 mm'], ['Adult, unfed', 16, 'about 3 mm'], ['Adult, engorged', 36, 'up to 10 mm']].map(([n, px, d]) =>
      h('figure', {}, h('i', { style: `width:${px}px;height:${px}px`, 'aria-hidden': 'true' }), h('figcaption', {}, n, h('br'), h('span', { class: 'muted small' }, d)))))));

  // species guide
  root.append(h('section', { class: 'section' }, h('h2', {}, 'Species identification guide'),
    h('p', { class: 'muted' }, 'Six ticks you may meet in the UK. Five appear in the sightings data; the castor bean tick is included because it is the most common Lyme disease carrier. These are illustrations, not photographs; for a firm identification ask a vet or use a tick identification service.'),
    h('div', { class: 'grid g3', style: 'margin-top:14px' }, edu.species.map((s, i) => h('article', { class: 'card sp-card' },
      h('div', { class: 'sp-top' }, h('div', { class: 'sp-art' }, tickArt(C().palette[i % C().palette.length])), h('div', {}, h('h3', {}, s.species), h('div', { class: 'latin' }, s.latin_name),
        s.in_dataset ? h('span', { class: 'badge badge-info', style: 'margin-top:6px' }, `${fmt(s.sightings)} sightings in the data`) : h('span', { class: 'badge badge-medium', style: 'margin-top:6px' }, 'Not in this dataset'))),
      h('p', { style: 'margin:0;font-weight:600' }, s.headline),
      h('dl', {}, ...[['Size', s.size], ['What it looks like', s.look], ['Where it lives', s.habitat], ['Hosts', s.hosts], ['Why it matters', s.why]].map(([k, v]) => h('div', {}, h('dt', {}, k), h('dd', {}, v)))))))));

  // seasonal chart
  const sel = h('select', { id: 'learn-city', onchange: (e) => drawSeason(e.target.value) }, h('option', { value: '' }, 'All UK cities'), cityGroups.map((c) => h('option', { value: c.name }, `${c.name} (${fmt(c.sightings)})`)));
  const sc = chartBox('Sightings by month of year', 'tall');
  root.append(h('section', { class: 'section' }, h('h2', {}, 'When are ticks most active near you?'),
    h('div', { class: 'card' }, h('div', { class: 'row-between' }, h('p', { class: 'muted', id: 'season-note', style: 'margin:0', 'aria-live': 'polite' }, ''), h('label', { class: 'field' }, h('span', {}, 'Choose a city'), sel)), sc.box)));
  window.__seasonCanvas = sc.canvas;
  drawSeason('');

  // prevention
  root.append(h('section', { class: 'section' }, h('h2', {}, 'Preventing tick bites'),
    h('div', { class: 'grid g3' }, edu.prevention_tips.map((t) => h('div', { class: 'card tip' }, h('div', { class: 'ic' }, icon(t.icon)), h('div', {}, h('h3', {}, t.title), h('p', {}, t.text)))))));

  // daily tick check (interactive, purely client-side)
  const areas = ['Scalp, hairline and behind the ears', 'Neck and armpits', 'Waist, belly button and groin', 'Behind the knees and between the legs', 'Between the toes and ankles', 'Your children, and any pets that came with you'];
  const bar = h('i'); const done = h('span', { class: 'small muted', 'aria-live': 'polite' }, `0 of ${areas.length} checked`);
  const boxes = areas.map((a) => { const cb = h('input', { type: 'checkbox' }); cb.addEventListener('change', () => { const n = boxes.filter((b) => b.checked).length; bar.style.width = `${(n / areas.length) * 100}%`; done.textContent = n === areas.length ? 'All checked. Well done!' : `${n} of ${areas.length} checked`; }); return cb; });
  root.append(h('section', { class: 'section' }, h('div', { class: 'grid g2' },
    h('div', { class: 'card' }, h('h2', {}, 'Your after-outdoors tick check'), h('p', { class: 'sub' }, 'Tick-bite prevention is mostly a habit. Tick these off after each walk.'),
      h('div', { class: 'progress', role: 'presentation' }, bar), done,
      h('ul', { class: 'checklist', style: 'margin-top:12px' }, areas.map((a, i) => h('li', {}, h('label', {}, boxes[i], h('span', {}, a)))))),
    h('div', { class: 'card' }, h('h2', {}, 'Why ticks are hard to spot'), h('p', { class: 'sub' }, 'Know where to look.'),
      h('p', {}, 'Ticks prefer warm, moist, hidden places, and their bite is usually painless, so many people never feel one. Nymphs are about the size of a poppy seed and are easy to mistake for a freckle.'),
      h('p', {}, 'A tick that is attached for less time has less chance to pass on infection, which is why checking and removing quickly matters more than anything else on this page.'),
      h('a', { class: 'btn btn-secondary btn-sm', href: '#/report' }, icon('plus'), 'Found one? Report it')))));

  // removal
  root.append(h('section', { class: 'section' }, h('div', { class: 'grid g2' },
    h('div', { class: 'card' }, h('h2', {}, 'How to remove a tick safely'), h('p', { class: 'sub' }, 'Remove it as soon as you find it.'), h('ol', { class: 'steps' }, edu.removal_steps.map((t) => h('li', {}, t)))),
    h('div', { style: 'display:grid;gap:14px;align-content:start' },
      h('div', { class: 'callout', role: 'note' }, icon('alert'), h('div', {}, h('b', {}, 'When to get help'), h('br'), edu.see_a_professional)),
      h('div', { class: 'callout', style: 'background:#e8f0fb;border-color:#c4d7f1;color:#1d4f91' }, icon('info'), h('div', {}, h('b', {}, 'Seen a tick?'), h('br'), 'Add it to the map so others can see where ticks are active. ', h('a', { href: '#/report', style: 'color:inherit;font-weight:700' }, 'Report a sighting')))))));
  root.append(h('p', { class: 'small muted', style: 'margin-top:20px' }, edu.disclaimer));
}

async function drawSeason(city) {
  const canvas = window.__seasonCanvas, note = $('#season-note');
  try {
    const s = await get('/reports/seasonality', city ? { location: city } : {});
    const peak = s.months.findIndex((m) => m.month === s.peak_month);
    note.textContent = s.total_sightings ? `${city || 'Across the UK'}: activity peaks in ${s.peak_month} (${fmt(s.months[peak].sightings)} sightings, ${s.months[peak].seasonal_index}x an average month).` : 'No sightings for this city yet.';
    canvas.setAttribute('aria-label', `Sightings by month in ${city || 'the UK'}. ${note.textContent}`);
    mkChart(charts, 'season', canvas, { type: 'bar', data: { labels: s.months.map((m) => m.month), datasets: [{ label: 'Sightings', data: s.months.map((m) => m.sightings), backgroundColor: s.months.map((_, i) => (i === peak ? C().accent : C().primary)), borderRadius: 6 }] },
      options: { scales: { y: { beginAtZero: true, grid: { color: C().grid }, ticks: { precision: 0 } }, x: { grid: { display: false } } } } });
  } catch (e) { note.textContent = e.message; }
}
