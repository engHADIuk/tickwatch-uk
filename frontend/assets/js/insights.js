// Insights view: regional counts, trends, species mix, seasonality, explainable risk ranking, spikes and data quality.
import { $, h, icon, clear, fmt, fmtDate, skeleton, errorBox, mkChart, destroyCharts, chartBox, riskBadge, riskKey, C, alpha } from './util.js';
import { get } from './api.js';

const charts = {};
let seq = 0;

export const themeChanged = () => enter();

export async function enter() {
  const root = clear($('#insights-body'));
  const my = ++seq;
  root.append(h('div', { class: 'grid g4' }, [1, 2, 3, 4].map(() => h('div', { class: 'card' }, skeleton(2, 22)))), h('div', { style: 'height:18px' }), h('div', { class: 'card' }, skeleton(6, 18)));
  try {
    const [regions, cities, species, season, risk, anomalies, dq, trendY] = await Promise.all([
      get('/reports/regions'), get('/reports/regions', { group_by: 'city' }), get('/reports/species'), get('/reports/seasonality'),
      get('/insights/risk', { limit: 10 }), get('/insights/anomalies', { scope: 'region' }), get('/data-quality'), get('/reports/trends', { interval: 'year' })]);
    if (my !== seq) return;
    destroyCharts(charts); clear(root);
    render(root, { regions, cities, species, season, risk, anomalies, dq, trendY });
  } catch (e) { if (my === seq) { clear(root).append(errorBox(e, enter)); } }
}

function render(root, d) {
  const rng = d.dq.date_range;
  root.append(h('div', { class: 'grid g4' },
    stat(fmt(d.dq.stored_sightings), 'Sightings recorded'), stat(fmt(d.cities.groups.length), 'Cities with sightings'),
    stat(fmt(d.regions.groups.length), 'UK regions'), stat(fmt(d.dq.community_reports), 'Community reports')));

  // regions + trend
  const rc = chartBox('Sightings per region, horizontal bar chart', 'tall');
  const tc = chartBox('Sightings over time', 'tall');
  const trendToggle = h('div', { class: 'seg-sm', role: 'group', 'aria-label': 'Trend interval' }, ...[['year', 'Yearly'], ['month', 'Monthly'], ['week', 'Weekly']].map(([iv, label]) =>
    h('button', { type: 'button', 'aria-pressed': String(iv === 'year'), onclick: async (e) => { [...e.currentTarget.parentElement.children].forEach((b) => b.setAttribute('aria-pressed', String(b === e.currentTarget))); drawTrend(tc.canvas, (await get('/reports/trends', { interval: iv })), iv); } }, label)));
  root.append(h('div', { class: 'grid g2', style: 'margin-top:18px' },
    h('div', { class: 'card' }, h('h2', {}, 'Sightings per region'), h('p', { class: 'sub' }, 'Where ticks are reported most often.'), rc.box),
    h('div', { class: 'card' }, h('div', { class: 'row-between', style: 'margin-bottom:0' }, h('h2', {}, 'Trend over time'), trendToggle), h('p', { class: 'sub' }, `${fmtDate(rng.from)} to ${fmtDate(rng.to)}`), tc.box)));
  mkChart(charts, 'regions', rc.canvas, { type: 'bar', data: { labels: d.regions.groups.map((g) => g.name), datasets: [{ data: d.regions.groups.map((g) => g.sightings), backgroundColor: C().primary, borderRadius: 6 }] },
    options: { indexAxis: 'y', scales: { x: { beginAtZero: true, grid: { color: C().grid }, ticks: { precision: 0 } }, y: { grid: { display: false } } } } });
  drawTrend(tc.canvas, d.trendY, 'year');

  // species + seasonality
  const sc = chartBox('Share of sightings by species, doughnut chart', 'tall'), ss = chartBox('Sightings by month of year', 'tall');
  const legend = h('ul', { class: 'bars', style: 'margin-top:12px' }, d.species.species.map((s, i) => h('li', {}, h('span', {}, h('span', { 'aria-hidden': 'true', style: `display:inline-block;width:10px;height:10px;border-radius:3px;background:${C().palette[i % C().palette.length]};margin-right:8px` }), s.species), h('b', {}, `${fmt(s.sightings)} · ${s.share_pct}%`))));
  root.append(h('div', { class: 'grid g2', style: 'margin-top:18px' },
    h('div', { class: 'card' }, h('h2', {}, 'Species mix'), h('p', { class: 'sub' }, 'Which ticks are recorded.'), h('div', { style: 'max-width:300px;margin:0 auto' }, sc.box), legend),
    h('div', { class: 'card' }, h('h2', {}, 'Seasonality'), h('p', { class: 'sub' }, d.season.peak_month ? `Activity peaks in ${d.season.peak_month}.` : 'Sightings by month.'), ss.box)));
  mkChart(charts, 'species', sc.canvas, { type: 'doughnut', data: { labels: d.species.species.map((s) => s.species), datasets: [{ data: d.species.species.map((s) => s.sightings), backgroundColor: C().palette, borderWidth: 2, borderColor: C().surface }] }, options: { cutout: '62%' } });
  const peak = d.season.months.findIndex((m) => m.month === d.season.peak_month);
  mkChart(charts, 'season', ss.canvas, { type: 'bar', data: { labels: d.season.months.map((m) => m.month), datasets: [{ data: d.season.months.map((m) => m.sightings), backgroundColor: d.season.months.map((_, i) => (i === peak ? C().accent : C().primary)), borderRadius: 6 }] },
    options: { scales: { y: { beginAtZero: true, grid: { color: C().grid }, ticks: { precision: 0 } }, x: { grid: { display: false } } } } });

  // risk + anomalies
  const top = Math.max(...d.risk.cities.map((c) => c.risk_score), 1);
  root.append(h('div', { class: 'grid g2', style: 'margin-top:18px' },
    h('div', { class: 'card' }, h('h2', {}, 'Recent-activity ranking'), h('p', { class: 'sub' }, `Explainable score out of 100 as of ${fmtDate(d.risk.as_of)} (the latest sighting in the data): recent volume 50%, growth 25%, seasonality 25%.`),
      h('ol', { style: 'list-style:none;margin:0;padding:0' }, d.risk.cities.map((c, i) => h('li', { class: 'risk-row' },
        h('span', { class: 'rank' }, i + 1),
        h('span', { class: 'name' }, h('button', { class: 'name', type: 'button', onclick: () => { location.hash = `#/map/${encodeURIComponent(c.city)}`; } }, c.city), h('span', { class: 'small muted' }, c.region)),
        h('span', { class: 'score' }, c.risk_score.toFixed(0)),
        h('span', { class: 'meter', 'aria-hidden': 'true' }, h('i', { style: `width:${(c.risk_score / top) * 100}%;background:var(--${riskKey(c.risk_level)})` })),
        h('span', { class: 'why-s' }, c.explanation))))),
    h('div', { style: 'display:grid;gap:18px;align-content:start' },
      h('div', { class: 'card' }, h('h2', {}, 'Unusual spikes'), h('p', { class: 'sub' }, `Months well above a region's normal level (z-score ${d.anomalies.z_threshold} or more).`),
        d.anomalies.anomalies.length
          ? h('ul', { class: 'bars' }, d.anomalies.anomalies.slice(0, 6).map((a) => h('li', {}, h('span', {}, h('b', {}, a.scope_key), ` · ${a.month}`), h('span', { class: `badge ${a.severity === 'high' ? 'badge-high' : 'badge-medium'}` }, `${a.sightings} vs ${a.expected} expected`))))
          : h('div', { class: 'empty' }, icon('check'), h('div', {}, h('b', {}, 'No unusual spikes detected')), h('div', { class: 'small' }, 'Monthly counts stay within normal variation in every region.'))),
      h('div', { class: 'card' }, h('h2', {}, 'Data quality'), h('p', { class: 'sub' }, 'Every record is validated, de-duplicated and logged before it reaches these charts.'),
        d.dq.last_sync ? h('div', { class: 'dq' },
          dq(d.dq.last_sync.status, 'Last sync'), dq(fmt(d.dq.last_sync.received), 'Received'), dq(fmt(d.dq.last_sync.accepted), 'Accepted'), dq(fmt(d.dq.last_sync.rejected), 'Quarantined')) : h('p', { class: 'muted' }, 'No sync has run yet.')))));
}

const stat = (v, l) => h('div', { class: 'card stat' }, h('b', {}, v), h('span', {}, l));
const dq = (v, l) => h('div', {}, h('b', {}, v), h('span', {}, l));

function drawTrend(canvas, t, iv) {
  const bar = iv === 'year';
  canvas.setAttribute('aria-label', `${iv}ly sightings across the UK; the busiest period is ${t.peak?.period} with ${t.peak?.sightings}.`);
  mkChart(charts, 'trend', canvas, { type: bar ? 'bar' : 'line',
    data: { labels: t.series.map((p) => p.period), datasets: [{ label: 'Sightings', data: t.series.map((p) => p.sightings), backgroundColor: bar ? C().primary : alpha(C().primary, 0.14), borderColor: C().primary, borderWidth: bar ? 0 : 2, borderRadius: 6, fill: !bar, tension: 0.25, pointRadius: 0 },
      ...(bar ? [] : [{ label: '3-period average', data: t.series.map((p) => p.moving_avg_3), borderColor: C().accent, borderWidth: 2, pointRadius: 0, tension: 0.3, fill: false }])] },
    options: { plugins: { legend: { display: !bar, position: 'bottom', labels: { boxWidth: 12 } } }, interaction: { mode: 'index', intersect: false },
      scales: { y: { beginAtZero: true, grid: { color: C().grid }, ticks: { precision: 0 } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 10, maxRotation: 0 } } } } });
}
