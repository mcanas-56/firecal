// Daily calendar: one month at a time, Monday–Sunday, coloured by quartiles of the
// non-zero daily counts for the selected area and year. Ported from the prototype.
import { $, state, onRender, iso, shortDate, selectedPeriod, setYear, setDate, stopPlayback } from './state.js';

const NAMES = ['No detections', 'Lower', 'Moderate', 'High', 'Very high'];
const COLOURS = ['#34463d', '#91aa64', '#d9c46c', '#e69950', '#d9684c'];

// 25th / 50th / 75th percentile of the non-zero daily totals for this area and year.
export function heatThresholds() {
  const v = Object.entries(state.archive)
    .filter(([day]) => day.startsWith(String(state.year)))
    .map(([, d]) => d[state.area]?.total)
    .filter((n) => n > 0)
    .sort((a, b) => a - b);
  return [0.25, 0.5, 0.75].map((q) => (v.length ? v[Math.min(v.length - 1, Math.floor((v.length - 1) * q))] : 0));
}

export function levelFor(total, thresholds) {
  if (total === undefined) return -1;            // no data
  if (total === 0) return 0;                      // no detections
  return 1 + thresholds.filter((t) => total > t).length;
}

function fillYears() {
  const sel = $('calendar-year');
  if (sel.options.length === state.years.length) return;
  sel.replaceChildren(...state.years.map((y) => new Option(String(y), String(y))));
}

function renderCalendar() {
  fillYears();
  const { year, area, calMonth } = state;
  const thresholds = heatThresholds();
  const p = selectedPeriod();
  $('calendar-source').textContent = year + ' · NASA FIRMS';
  $('calendar-year').value = String(year);
  $('cal-month').textContent = new Date(Date.UTC(year, calMonth, 1)).toLocaleDateString('en', { month: 'long', timeZone: 'UTC' });
  $('cal-prev').disabled = calMonth === 0;
  $('cal-next').disabled = calMonth === 11;

  const host = $('heatmap-days');
  host.replaceChildren();
  const offset = (new Date(Date.UTC(year, calMonth, 1)).getUTCDay() + 6) % 7;   // Monday first
  for (let i = 0; i < offset; i++) host.appendChild(document.createElement('span'));
  const days = new Date(Date.UTC(year, calMonth + 1, 0)).getUTCDate();
  for (let day = 1; day <= days; day++) {
    const date = iso(new Date(Date.UTC(year, calMonth, day)));
    const entry = state.archive[date]?.[area];
    const level = levelFor(entry?.total, thresholds);
    const inPeriod = date >= p.start && date <= p.end;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'heat-day' + (inPeriod ? ' in-period' : '') + (level === -1 ? ' missing' : '');
    btn.dataset.date = date;
    if (level !== -1) btn.style.background = COLOURS[level];
    btn.innerHTML = '<span>' + day + '</span><small>' + (entry ? entry.total.toLocaleString() : '—') + '</small>';
    const label = date + ' · ' + (entry ? entry.total.toLocaleString() + ' detections · ' + NAMES[level] : 'no data');
    btn.setAttribute('aria-label', label);
    btn.title = label;
    btn.setAttribute('aria-pressed', String(inPeriod));
    btn.onclick = () => selectDay(date);
    host.appendChild(btn);
  }

  $('heat-thresholds').textContent = Object.keys(state.archive).length
    ? 'Positive-day quartile boundaries: ' + thresholds.map((n) => n.toLocaleString()).join(' / ') + ' detections.'
    : 'Loading daily data…';
  $('calendar-selection').textContent = 'Selected ' + state.scale + ': ' + shortDate(p.start)
    + (p.end !== p.start ? ' – ' + shortDate(p.end) : '') + ' · ' + area
    + '. Weeks run Monday–Sunday; year-edge weeks are clipped to the selected year.';
}

// Clicking a day selects it, switches the timeline to Days and scrolls to the globe.
function selectDay(date) {
  stopPlayback();
  state.scale = 'day';
  setDate(date);
  document.dispatchEvent(new CustomEvent('firecal:fit-area'));
  requestAnimationFrame(() => {
    $('map').scrollIntoView({ behavior: 'instant', block: 'center' });
    $('globe').focus({ preventScroll: true });
  });
}

export function initCalendar() {
  $('calendar-year').onchange = () => { stopPlayback(); setYear(Number($('calendar-year').value)); };
  $('cal-prev').onclick = () => { state.calMonth = Math.max(0, state.calMonth - 1); renderCalendar(); };
  $('cal-next').onclick = () => { state.calMonth = Math.min(11, state.calMonth + 1); renderCalendar(); };
  onRender(renderCalendar);
}
