// Entry point: wires the features together and loads web/data/archive.json.
import { $, state, onRender, render, selectedPeriod, periodDays, periodLabel, setArea, MAX_MARKERS } from './state.js';
import { initCalendar } from './calendar.js';
import { initGlobe, setPoints, fitArea } from './globe.js';
import { initTimeline } from './timeline.js';
import { initTheme } from './theme.js';
import { initNav } from './nav.js';

// Globe markers, map caption and stat cards for the selected area and period.
function renderSelection() {
  const p = selectedPeriod();
  const label = periodLabel(p);
  const area = state.area;
  const days = periodDays(p);
  const entries = days.map((d) => state.archive[d]?.[area]);
  const covered = entries.every(Boolean);
  const all = [];
  entries.forEach((e, i) => { if (e) e.points.forEach((pt) => all.push([...pt, days[i]])); });
  const every = Math.max(1, Math.ceil(all.length / MAX_MARKERS));
  const pts = all.filter((_, i) => i % every === 0);
  const count = entries.reduce((n, e) => n + (e?.total || 0), 0);

  $('region').value = area;
  $('map-label').textContent = 'ARCHIVE · ' + label;
  $('hotspot-count').textContent = covered ? count.toLocaleString() : '—';
  $('count-note').textContent = `${pts.length} sampled points shown · ${area}`;
  $('window-stat').textContent = days.length + ' ' + (days.length === 1 ? 'day' : 'days');
  $('window-note').textContent = label + ' · ' + state.year;
  $('map-detail').textContent = `${area} · ${label} · ${covered ? count.toLocaleString() : 'Incomplete data'} detections · ${pts.length} sampled markers`;
  const empty = $('empty-map');
  empty.hidden = pts.length > 0;
  empty.textContent = state.archiveError ? 'Archive could not load. Start the app with: python -m src.serve'
    : !covered ? 'Archive loading or missing coverage.' : 'No detections in this period.';
  setPoints($('show-hotspots').checked ? pts : []);
}

function init() {
  initTheme();
  initNav();
  initGlobe();
  initCalendar();
  initTimeline();
  onRender(renderSelection);
  $('region').onchange = () => { setArea($('region').value); fitArea(); };
  $('show-hotspots').onchange = renderSelection;
  render();

  fetch('data/archive.json')
    .then((r) => { if (!r.ok) throw new Error('Archive unavailable'); return r.json(); })
    .then((data) => {
      state.archive = data;
      state.years = [...new Set(Object.keys(data).map((d) => Number(d.slice(0, 4))))].sort();
      if (!state.years.includes(state.year)) {
        state.year = state.years[state.years.length - 1];
        state.date = state.year + '-01-01';
        state.calMonth = 0;
      }
      render();
    })
    .catch(() => { state.archiveError = true; render(); });
}

init();
