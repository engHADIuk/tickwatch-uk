// Report-a-sighting view: accessible form with live validation, warnings, photo upload and clear success / error states.
import { $, h, icon, clear, toast, haversineKm, fmtDate } from './util.js';
import { get, post, ApiError } from './api.js';

const MAX_MB = 5, NOTE_MAX = 500, TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const S = { opts: null, file: null, form: null, built: false, submitting: false };

export async function enter({ query }) {
  const root = $('#report-body');
  if (!S.built) { await build(root); S.built = true; }
  const city = query.get('city');
  if (city && S.form) { S.form.location.value = city; showSummaryClear(); }
  else if (!S.form) return;
}

const nowLocal = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };

async function build(root) {
  try { S.opts = await get('/options'); } catch (e) { root.append(h('div', { class: 'err-box', role: 'alert' }, e.message)); return; }
  const byRegion = {};
  S.opts.cities.forEach((c) => (byRegion[c.region] ||= []).push(c.city));

  const f = (name, label, control, { hint, required = true } = {}) => h('div', { class: 'field', 'data-field': name },
    h('label', { for: name }, h('span', {}, label, required ? h('span', { class: 'sr-only' }, ' (required)') : h('span', { class: 'muted', style: 'font-weight:500' }, ' optional'))), control,
    hint ? h('p', { class: 'field-msg hint', id: `${name}-hint` }, hint) : null,
    h('div', { id: `${name}-msg`, 'aria-live': 'polite' }));

  const date = h('input', { type: 'datetime-local', id: 'date', name: 'date', max: nowLocal(), value: nowLocal(), required: true });
  const location_ = h('select', { id: 'location', name: 'location', required: true }, h('option', { value: '' }, 'Choose the nearest city…'),
    Object.keys(byRegion).sort().map((r) => h('optgroup', { label: r }, byRegion[r].map((c) => h('option', { value: c }, c)))));
  const species = h('select', { id: 'species', name: 'species', required: true }, h('option', { value: '' }, 'Choose a species…'),
    S.opts.species.map((s) => h('option', { value: s }, s)), h('option', { value: 'Not sure' }, 'Not sure'));
  const notes = h('textarea', { id: 'notes', name: 'notes', rows: '4', maxlength: '800', placeholder: 'Where was it? On a person or a pet? Anything else useful.' });
  const counter = h('span', { class: 'counter', id: 'notes-counter' }, `0/${NOTE_MAX}`);
  notes.addEventListener('input', () => { const n = notes.value.length; counter.textContent = `${n}/${NOTE_MAX}`; counter.style.color = n > NOTE_MAX ? 'var(--red-700)' : ''; });

  const locate = h('button', { type: 'button', class: 'btn btn-ghost btn-sm', id: 'locate' }, icon('locate'), 'Use my location');
  locate.addEventListener('click', useLocation);

  const fileInput = h('input', { type: 'file', id: 'image', name: 'image', accept: TYPES.join(','), 'aria-describedby': 'image-hint image-msg' });
  const drop = h('label', { class: 'drop', for: 'image', id: 'drop' }, icon('upload'), h('span', {}, 'Add a photo'), h('span', { class: 'muted small', style: 'font-weight:500' }, `Drag a picture here or click to browse. JPEG, PNG or WebP, up to ${MAX_MB} MB.`), fileInput);
  const preview = h('div', { id: 'preview' });
  fileInput.addEventListener('change', () => setFile(fileInput.files[0] || null));
  for (const ev of ['dragenter', 'dragover']) drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('is-over'); });
  for (const ev of ['dragleave', 'drop']) drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('is-over'); });
  drop.addEventListener('drop', (e) => { const fl = e.dataTransfer.files[0]; if (fl) { const dt = new DataTransfer(); dt.items.add(fl); fileInput.files = dt.files; setFile(fl); } });

  const summary = h('div', { id: 'summary', tabindex: '-1' });
  const submit = h('button', { type: 'submit', class: 'btn btn-primary', id: 'submit' }, 'Submit report');
  const form = h('form', { id: 'report-form', novalidate: true, class: 'card form-grid', 'aria-labelledby': 'h-report' }, summary,
    h('div', { class: 'field-row' }, f('date', 'When did you see it?', date), h('div', {}, f('location', 'Nearest city', location_), h('div', { style: 'margin-top:4px' }, locate), h('div', { id: 'locate-msg', 'aria-live': 'polite' }))),
    f('species', 'Species', species, { hint: 'Not sure? Choose “Not sure” and add a photo. See the species guide in Learn.' }),
    h('div', { class: 'field', 'data-field': 'notes' }, h('label', { for: 'notes' }, h('span', {}, 'Notes ', h('span', { class: 'muted', style: 'font-weight:500' }, 'optional')), counter), notes, h('div', { id: 'notes-msg', 'aria-live': 'polite' })),
    h('div', { class: 'field', 'data-field': 'image' }, h('span', { id: 'image-label' }, 'Photo ', h('span', { class: 'muted', style: 'font-weight:500' }, 'optional')), drop, preview, h('p', { class: 'field-msg hint', id: 'image-hint' }, 'A clear close-up helps experts confirm the species.'), h('div', { id: 'image-msg', 'aria-live': 'polite' })),
    h('div', { class: 'row-between', style: 'margin:0' }, h('p', { class: 'small muted', style: 'margin:0;max-width:340px' }, 'We store the date, city, species, notes and photo you provide. We do not ask for your name or exact address.'), submit));
  S.form = form;
  form.addEventListener('submit', onSubmit);
  form.addEventListener('focusout', (e) => { if (e.target.name && ['date', 'location', 'species', 'notes'].includes(e.target.name)) validateField(e.target.name); });
  date.addEventListener('change', () => validateField('date'));

  const aside = h('aside', { class: 'card side-note' }, h('h2', {}, 'Why report?'),
    h('ul', {}, h('li', {}, 'Helps other owners and walkers see where ticks are active.'), h('li', {}, 'Gives vets an early signal of rising activity.'),
      h('li', {}, 'Photos make reports far more useful for identifying species.')),
    h('hr', { style: 'border:0;border-top:1px solid var(--line);margin:16px 0' }), h('h3', {}, 'Found a tick on someone?'),
    h('p', { class: 'small muted' }, 'Remove it safely first with a tick remover or fine-tipped tweezers. ', h('a', { href: '#/learn' }, 'See how')));
  root.append(h('div', { class: 'report-layout' }, h('div', { id: 'form-slot' }, form), aside));
}

// ---------- validation ----------
const msgBox = (name) => $(`#${name}-msg`);
function setMsg(name, kind, text) {
  const box = msgBox(name), wrap = $(`[data-field="${name}"]`);
  clear(box); wrap?.classList.toggle('has-error', kind === 'error');
  const ctl = $(`#${name}`);
  if (ctl) { if (kind === 'error') ctl.setAttribute('aria-invalid', 'true'); else ctl.removeAttribute('aria-invalid'); }
  if (text) box.append(h('p', { class: `field-msg ${kind}` }, icon(kind === 'error' ? 'alert' : 'info'), text));
}
function validateField(name) {
  const f = S.form, v = f[name].value.trim();
  if (name === 'date') {
    if (!v) return setMsg('date', 'error', 'Please enter when you saw the tick.'), false;
    const t = new Date(v);
    if (Number.isNaN(+t)) return setMsg('date', 'error', 'That date is not valid.'), false;
    if (t > new Date(Date.now() + 5 * 60000)) return setMsg('date', 'error', 'The sighting cannot be in the future.'), false;
    if (t.getFullYear() < 2000) return setMsg('date', 'error', 'Sightings before 2000 are not accepted.'), false;
    const days = (Date.now() - t) / 864e5;
    if (days > 365) setMsg('date', 'warn', `This was ${Math.round(days / 365 * 10) / 10} years ago. You can still submit it, but recent sightings are more useful.`);
    else setMsg('date', null);
    return true;
  }
  if (name === 'location') { if (!v) return setMsg('location', 'error', 'Please choose the nearest city.'), false; setMsg('location', null); return true; }
  if (name === 'species') { if (!v) return setMsg('species', 'error', 'Please choose a species, or “Not sure”.'), false; setMsg('species', null); return true; }
  if (name === 'notes') { if (v.length > NOTE_MAX) return setMsg('notes', 'error', `Notes must be ${NOTE_MAX} characters or fewer (you have ${v.length}).`), false; setMsg('notes', null); return true; }
  return true;
}

function setFile(file) {
  const prev = clear($('#preview')); S.file = null; $('#drop').classList.remove('has-error');
  if (!file) { setMsg('image', null); return; }
  if (!TYPES.includes(file.type)) { S.form.image.value = ''; setMsg('image', 'error', 'Photos must be JPEG, PNG or WebP images.'); $('#drop').classList.add('has-error'); return; }
  if (file.size > MAX_MB * 1024 * 1024) { S.form.image.value = ''; setMsg('image', 'error', `That photo is ${(file.size / 1048576).toFixed(1)} MB. The limit is ${MAX_MB} MB.`); $('#drop').classList.add('has-error'); return; }
  S.file = file; setMsg('image', null);
  const url = URL.createObjectURL(file);
  prev.append(h('div', { class: 'preview' }, h('img', { src: url, alt: 'Preview of the photo you selected', onload: () => URL.revokeObjectURL(url) }),
    h('div', { class: 'meta' }, h('b', {}, file.name), `${(file.size / 1048576).toFixed(2)} MB`),
    h('button', { type: 'button', class: 'icon-btn', 'aria-label': 'Remove photo', onclick: () => { S.form.image.value = ''; setFile(null); S.form.image.focus(); } }, icon('trash'))));
}

function useLocation() {
  const out = clear($('#locate-msg'));
  if (!navigator.geolocation) { out.append(h('p', { class: 'field-msg warn' }, icon('info'), 'Location is not available in this browser.')); return; }
  out.append(h('p', { class: 'field-msg hint' }, 'Finding your nearest city…'));
  navigator.geolocation.getCurrentPosition((pos) => {
    const me = { lat: pos.coords.latitude, lng: pos.coords.longitude };
    const best = S.opts.cities.map((c) => ({ ...c, km: haversineKm(me, c) })).sort((a, b) => a.km - b.km)[0];
    clear(out);
    if (best.km > 120) out.append(h('p', { class: 'field-msg warn' }, icon('info'), `The nearest city we know is ${best.city}, about ${Math.round(best.km)} km away. Please check it.`));
    else out.append(h('p', { class: 'field-msg hint' }, `Nearest city: ${best.city}`));
    S.form.location.value = best.city; validateField('location');
  }, () => { clear(out).append(h('p', { class: 'field-msg warn' }, icon('info'), 'We could not get your location. Please choose a city from the list.')); }, { timeout: 8000 });
}

// ---------- submit ----------
const LABELS = { date: 'When did you see it?', location: 'Nearest city', species: 'Species', notes: 'Notes', image: 'Photo' };
function showSummary(errors) {
  const box = clear($('#summary'));
  if (!errors.length) return;
  box.append(h('div', { class: 'alert error', role: 'alert' }, icon('alert'), h('div', {}, h('b', {}, `Please fix ${errors.length} problem${errors.length > 1 ? 's' : ''} before submitting`),
    h('ul', {}, errors.map((e) => h('li', {}, h('a', { href: `#${e.field}`, onclick: (ev) => { ev.preventDefault(); $(`#${e.field}`)?.focus(); } }, LABELS[e.field] || e.field), ': ', e.problem))))));
  box.focus();
}
const showSummaryClear = () => clear($('#summary'));

async function onSubmit(ev) {
  ev.preventDefault();
  if (S.submitting) return;
  const errs = [];
  for (const n of ['date', 'location', 'species', 'notes']) if (!validateField(n)) errs.push({ field: n, problem: $(`#${n}-msg .field-msg`)?.textContent || 'Invalid' });
  if ($('#drop').classList.contains('has-error')) errs.push({ field: 'image', problem: $('#image-msg .field-msg')?.textContent || 'Invalid photo' });
  if (errs.length) { showSummary(errs); return; }
  showSummary([]);
  const fd = new FormData();
  for (const n of ['date', 'location', 'species', 'notes']) fd.append(n, S.form[n].value.trim());
  if (S.file) fd.append('image', S.file);
  setBusy(true);
  try {
    const created = await post('/sightings', fd);
    window.dispatchEvent(new Event('tw:data-changed'));
    showSuccess(created, !S.file);
  } catch (e) { handleError(e); }
  finally { setBusy(false); }
}

function setBusy(on) {
  S.submitting = on; const b = $('#submit'); if (!b) return;
  b.disabled = on; b.setAttribute('aria-busy', String(on)); b.textContent = on ? 'Submitting…' : 'Submit report';
}

function handleError(e) {
  if (e instanceof ApiError && e.status === 422 && Array.isArray(e.details)) {
    e.details.forEach((d) => { if (d.field !== 'image' || true) { setMsg(d.field, 'error', d.problem); if (d.field === 'image') $('#drop').classList.add('has-error'); } });
    showSummary(e.details); return;
  }
  const text = e.status === 429 ? `You are sending reports too quickly. Please wait ${e.retryAfter || 'a few'} seconds and try again.`
    : e.status === 409 ? 'This sighting looks like one that has already been reported. Thank you!'
    : e.message;
  const box = clear($('#summary'));
  box.append(h('div', { class: `alert ${e.status === 409 ? 'info' : 'error'}`, role: 'alert' }, icon(e.status === 409 ? 'info' : 'alert'), h('div', {}, text)));
  box.focus();
}

function showSuccess(s, noPhoto) {
  const slot = clear($('#form-slot'));
  slot.append(h('div', { class: 'card success-card', role: 'status' },
    h('div', { class: 'tick' }, icon('check')), h('h2', { id: 'success-title', tabindex: '-1' }, 'Thank you. Your report is on the map'),
    h('p', { class: 'muted' }, `${s.species} in ${s.location} on ${fmtDate(s.date)}. Reference ${s.id}.`),
    noPhoto ? h('p', { class: 'small muted' }, 'Tip: next time, a photo helps confirm the species.') : null,
    h('div', { class: 'actions' }, h('a', { class: 'btn btn-primary', href: `#/map/${encodeURIComponent(s.location)}` }, icon('map'), `See ${s.location} on the map`),
      h('button', { class: 'btn btn-secondary', type: 'button', onclick: reset }, 'Report another'))));
  $('#success-title').focus(); toast('Report submitted');
}

function reset() {
  S.built = false; S.file = null; S.form = null; clear($('#report-body'));
  enter({ query: new URLSearchParams() }).then(() => $('#date')?.focus());
}
