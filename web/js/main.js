// Entry point: wires the features together and loads the data src/web_data.py builds
// from data/*.csv (served by `python -m src.serve` at /data/archive.json and /data/monthly.json).
import { $, state, onRender, render, selectedPeriod, periodDays, periodLabel, setArea, setMode, MAX_MARKERS } from './state.js';
import { initCalendar } from './calendar.js';
import { initGlobe, setPoints } from './globe.js';
import { initTimeline } from './timeline.js';
import { initTheme } from './theme.js';
import { initNav } from './nav.js';
import { initMonthly } from './monthly.js';
import { initTicker } from './ticker.js';
import { initOutlook, outlookReady, renderOutlook } from './outlook.js';

const DEFAULT_AREA = 'Canada';
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Area controls (US-03): built from the areas in the data (Canada first, then A–Z); the
// switch above the calendar and the globe's select stay in step.
function areasInData() {
  const found = Object.keys(state.monthly?.areas || {}).sort();
  return found.includes(DEFAULT_AREA) ? [DEFAULT_AREA, ...found.filter((a) => a !== DEFAULT_AREA)] : found;
}

function buildAreaControls(areas) {
  const sw = document.querySelector('.area-switch');
  sw.replaceChildren(...areas.map((a) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'scale-option';
    b.dataset.area = a;
    b.textContent = a;
    b.onclick = () => setArea(a);
    return b;
  }));
  $('region').replaceChildren(...areas.map((a) => new Option(a, a)));
}

function renderArea() {
  document.querySelectorAll('[data-area]').forEach((btn) => {
    const active = btn.dataset.area === state.area;
    btn.classList.toggle('selected', active);
    btn.setAttribute('aria-pressed', String(active));
  });
  $('region').value = state.area;
  const sensor = state.monthly?.areas?.[state.area]?.daily_sensor?.[state.year] || 'VIIRS S-NPP';
  $('daily-sensor').textContent = sensor;
  $('calendar-source').textContent = `${state.year} · NASA FIRMS · ${sensor}`;
}

// Live view is part of the MVP layout but has no feed yet: it says so instead of showing
// invented hotspots, and any date choice returns to Past data.
// Outlook (US-18) shows the fire outlook from outlook.json, or why it isn't available.
function renderMode() {
  const live = state.mode === 'live';
  const outlook = state.mode === 'outlook';
  const ready = outlook && outlookReady();
  for (const [id, on] of [['live-mode', live], ['past-mode', state.mode === 'past'], ['outlook-mode', outlook]]) {
    $(id).classList.toggle('selected', on);
    $(id).setAttribute('aria-pressed', String(on));
  }
  $('live-note').hidden = !live;
  $('date-controls').hidden = state.mode !== 'past';
  $('live-panel').hidden = !live;
  $('outlook-controls').hidden = !ready;
  $('outlook-unavailable').hidden = !outlook || ready;
  $('outlook-legend').hidden = !ready;
  $('hotspot-legend').hidden = outlook;
  $('time-explorer').hidden = outlook;   // the time explorer is for the archive
  $('season-strip').hidden = !ready;     // the Predictions strip takes its place
}

// Stat card titles for Past data and Live view; the outlook sets its own.
function resetCards() {
  $('count-title').textContent = 'Hotspot detections';
  $('count-tag').textContent = 'NASA FIRMS';
  $('window-title').textContent = 'Observation window';
  $('month-title').textContent = 'Harmonized month';
}

function renderOutlookMode() {
  if (outlookReady()) { renderOutlook(); return; }
  const reason = state.outlook?.status === 'unavailable' ? state.outlook.reason
    : state.outlook ? 'No predictions for this area.' : 'Loading the predictions…';
  $('outlook-reason').textContent = reason;
  $('map-label').textContent = 'PREDICTIONS · NOT AVAILABLE';
  for (const id of ['hotspot-count', 'window-stat', 'month-stat']) $(id).textContent = '—';
  for (const id of ['count-note', 'window-note', 'month-note']) $(id).textContent = '';
  $('map-detail').textContent = `${state.area} · Predictions not available: ${reason}`;
  $('empty-map').hidden = true;
  setPoints([]);
}

function renderLive() {
  $('map-label').textContent = 'LIVE VIEW · COMING SOON';
  $('hotspot-count').textContent = '—';
  $('count-note').textContent = `Live feed coming soon · ${state.area}`;
  $('window-stat').textContent = '24 hours';
  $('window-note').textContent = 'Live view preview';
  $('map-detail').textContent = `${state.area} · Live view is coming soon · choose Past data to explore the archive`;
  $('empty-map').hidden = true;
  setPoints([]);
}

// Globe markers, map caption and stat cards for the selected area and period.
function renderSelection() {
  resetCards();
  if (state.mode === 'live') { renderLive(); return; }
  if (state.mode === 'outlook') { renderOutlookMode(); return; }
  const p = selectedPeriod();
  const label = periodLabel(p);
  const area = state.area;
  const days = periodDays(p);
  const entries = days.map((d) => state.archive[d]?.[area]);
  const missing = entries.filter((e) => !e).length;
  const covered = missing < entries.length;          // at least one day with data
  const all = [];
  entries.forEach((e, i) => { if (e) e.points.forEach((pt) => all.push([...pt, days[i]])); });
  const every = Math.max(1, Math.ceil(all.length / MAX_MARKERS));
  const pts = all.filter((_, i) => i % every === 0);
  const count = entries.reduce((n, e) => n + (e?.total || 0), 0);

  $('map-label').textContent = 'NASA FIRMS · ' + label;
  $('hotspot-count').textContent = covered ? count.toLocaleString() : '—';
  $('count-note').textContent = missing && covered
    ? `${missing} of ${days.length} days without data · ${area}`
    : `${pts.length} sampled points shown · ${area}`;
  $('window-stat').textContent = days.length + ' ' + (days.length === 1 ? 'day' : 'days');
  $('window-note').textContent = label + ' · ' + state.year;
  $('map-detail').textContent = `${area} · ${label} · ${covered ? count.toLocaleString() + ' detections' : 'no satellite data'}`
    + (missing && covered ? ` (${missing} days without data)` : '') + ` · ${pts.length} sampled markers`;

  const m = state.monthly?.areas?.[area]?.months.find((r) => r.year === state.year && r.month === state.calMonth + 1);
  $('month-stat').textContent = m && m.harmonized !== null ? Math.round(m.harmonized).toLocaleString() : '—';
  $('month-note').textContent = `Harmonized fire cell-days · ${MONTHS[state.calMonth]} ${state.year}`;

  const empty = $('empty-map');
  empty.hidden = pts.length > 0;
  empty.textContent = state.archiveError ? 'No fire data yet. See the steps at the top of the page.'
    : !covered ? 'No satellite data for this period.' : 'No detections in this period.';
  setPoints($('show-hotspots').checked ? pts : []);
}

async function loadJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + ' unavailable');
  return r.json();
}

async function loadData() {
  try {
    const [archive, monthly] = await Promise.all([loadJSON('data/archive.json'), loadJSON('data/monthly.json')]);
    if (monthly.status === 'no_data' || !Object.keys(archive).length) throw new Error('no data yet');
    state.archive = archive;
    state.monthly = monthly;
    // The outlook is optional: the rest of the page works without it.
    loadJSON('data/outlook.json').then((o) => { state.outlook = o; render(); })
      .catch(() => { state.outlook = { status: 'unavailable', reason: 'outlook.json could not be loaded.', areas: {} }; render(); });
    state.years = [...new Set(Object.keys(archive).map((d) => Number(d.slice(0, 4))))].sort();
    const areas = areasInData();
    buildAreaControls(areas);
    const wanted = new URLSearchParams(location.search).get('area');
    state.area = areas.includes(wanted) ? wanted : areas.includes(state.area) ? state.area : areas[0];
    document.dispatchEvent(new CustomEvent('firecal:fit-area'));
    if (!state.years.includes(state.year)) {
      state.year = state.years[state.years.length - 1];
      state.date = state.year + '-07-01';
      state.calMonth = 6;
    }
  } catch (e) {
    state.archiveError = true;
    $('no-data').hidden = false;
    document.body.classList.add('no-data-mode');
  }
  render();
}

function init() {
  initTheme();
  initNav();
  initGlobe();
  initCalendar();
  initMonthly();
  initTicker();
  initTimeline();
  initOutlook();
  onRender(renderMode);
  onRender(renderArea);
  onRender(renderSelection);

  document.querySelectorAll('[data-area]').forEach((btn) => { btn.onclick = () => setArea(btn.dataset.area); });
  $('region').onchange = () => setArea($('region').value);
  $('show-hotspots').onchange = renderSelection;
  $('live-mode').onclick = () => setMode('live');
  $('past-mode').onclick = () => setMode('past');
  $('outlook-mode').onclick = () => setMode('outlook');
  $('live-back').onclick = () => setMode('past');
  document.dispatchEvent(new CustomEvent('firecal:fit-area'));
  render();
  loadData();
}

init();
