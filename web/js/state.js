// Shared state and date helpers. Every feature module reads from `state` and calls the
// actions below; each action ends with render(), which redraws every feature, so the
// calendar, slider, date field, globe and stat cards always show the same selection.

export const $ = (id) => document.getElementById(id);

export const state = {
  archive: {},          // /data/archive.json: date -> area -> {total, frp, points: [[lat, lon, frp]]}
  monthly: null,        // /data/monthly.json: per area harmonized months, fit, season, daily sensor
  archiveError: false,
  years: [],            // years found in the archive
  year: 2023,
  area: 'Canada',
  scale: 'day',         // 'day' | 'week' | 'month'
  date: '2023-07-01',   // the selected day; the selected period is the one containing it
  calMonth: 6,          // month shown in the calendar (0 = January)
  periods: [],
  playTimer: null,
};

export const MAX_MARKERS = 300;

const renderers = [];
export function onRender(fn) { renderers.push(fn); }
export function render() {
  state.periods = makePeriods(state.scale, state.year);
  for (const fn of renderers) fn();
}

// ---- dates (all UTC so the calendar never shifts with the viewer's time zone) ----
export function iso(d) { return d.toISOString().slice(0, 10); }

export function shortDate(day) {
  return new Date(day + 'T12:00:00Z').toLocaleDateString('en', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

// Periods covering one year. Weeks run Monday–Sunday and are clipped at the year's edges.
export function makePeriods(scale, year) {
  const out = [];
  const last = new Date(Date.UTC(year, 11, 31));
  let start = new Date(Date.UTC(year, 0, 1));
  while (start.getUTCFullYear() === year) {
    let end = new Date(start);
    if (scale === 'week') end.setUTCDate(end.getUTCDate() + ((7 - end.getUTCDay()) % 7));
    else if (scale === 'month') end = new Date(Date.UTC(year, start.getUTCMonth() + 1, 0));
    if (end > last) end = new Date(last);
    out.push({ start: iso(start), end: iso(end) });
    start = new Date(end);
    start.setUTCDate(start.getUTCDate() + 1);
  }
  return out;
}

export function selectedPeriod() {
  return state.periods.find((p) => state.date >= p.start && state.date <= p.end) || state.periods[0];
}

export function periodDays(p) {
  const out = [];
  for (let d = new Date(p.start + 'T00:00:00Z'); iso(d) <= p.end; d.setUTCDate(d.getUTCDate() + 1)) out.push(iso(d));
  return out;
}

export function periodLabel(p) {
  return p.start === p.end ? shortDate(p.start) : shortDate(p.start) + ' – ' + shortDate(p.end);
}

// ---- actions ----
export function stopPlayback() {
  if (state.playTimer) clearInterval(state.playTimer);
  state.playTimer = null;
  const btn = $('play-dates');
  btn.textContent = '▶';
  btn.setAttribute('aria-label', 'Play through the year');
}

export function setDate(date) {
  const y = String(state.year);
  state.date = date && date.startsWith(y) ? date : y + '-01-01';
  state.calMonth = Number(state.date.slice(5, 7)) - 1;
  render();
}

export function setYearMonth(year, month) {
  state.year = year;
  setDate(`${year}-${String(month + 1).padStart(2, '0')}-01`);
}

export function setYear(year) {
  state.year = year;
  setDate(year + '-01-01');
}

export function setScale(scale) {
  state.scale = scale;
  setDate(state.date);   // also brings the calendar back to the selected month
}

// US-03: one area choice drives every section; kept in the address (?area=Argentina).
export function setArea(area) {
  state.area = area;
  try {
    const url = new URL(location.href);
    url.searchParams.set('area', area);
    history.replaceState(null, '', url);
  } catch (e) { /* address not updatable (e.g. file://): selection still works */ }
  document.dispatchEvent(new CustomEvent('firecal:fit-area'));
  setDate(state.date);
}
