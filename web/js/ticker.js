// Fire-activity ticker: the prototype's scrolling bar, filled from our data for the
// selected date or period, for every area. Per area it shows the activity level
// (same quartile colours as the calendar), the season status and the harmonized month
// compared with the same month in another year. Activity, not a danger rating.
import { $, state, onRender, selectedPeriod, periodDays, periodLabel } from './state.js';
import { heatThresholds, levelFor, NAMES, COLOURS } from './calendar.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const dot = (colour) => `<span class="dot" style="background:${colour}"></span>`;

function item(label, value, note = '') {
  return `<div class="ticker-item"><span>${esc(label)}</span><b>${value}</b>${note ? `<small>${esc(note)}</small>` : ''}</div>`;
}

function areaItems(area) {
  const p = selectedPeriod();
  const days = periodDays(p);
  const entries = days.map((d) => state.archive[d]?.[area]).filter(Boolean);
  const items = [];

  // 1. Activity in the selected period: mean daily count, coloured like the calendar.
  if (!entries.length) {
    items.push(item(area, dot('var(--line)') + 'No satellite data', periodLabel(p)));
  } else {
    const total = entries.reduce((n, e) => n + e.total, 0);
    const level = levelFor(Math.round(total / entries.length), heatThresholds(area, state.year));
    items.push(item(area, dot(COLOURS[level]) + esc(NAMES[level]),
      `${total.toLocaleString()} detection${total === 1 ? '' : 's'}`));
  }

  const info = state.monthly?.areas?.[area];
  // 2. Fire season status for the selected month.
  const s = info?.season;
  if (s && (s.status === 'ok' || s.status === 'year_round')) {
    const inSeason = s.months.includes(state.calMonth + 1);
    items.push(item(`${area} fire season`, `${MONTHS[s.start - 1]} – ${MONTHS[s.end - 1]}`,
      inSeason ? (s.peak === state.calMonth + 1 ? 'Peak month' : 'In season') : 'Off season'));
  }

  // 3. Harmonized month vs the same month in the closest other year.
  const month = state.calMonth + 1;
  const rows = (info?.months || []).filter((r) => r.month === month && r.harmonized !== null);
  const now = rows.find((r) => r.year === state.year);
  if (now) {
    const other = rows.filter((r) => r.year !== state.year).sort((a, b) => Math.abs(a.year - state.year) - Math.abs(b.year - state.year))[0];
    let note = 'harmonized cell-days';
    if (other && other.harmonized > 0) {
      const pct = Math.round((now.harmonized / other.harmonized - 1) * 100);
      note = `${pct >= 0 ? '+' : ''}${pct}% vs ${MONTHS[month - 1]} ${other.year}`;
    }
    items.push(item(`${area} · ${MONTHS[month - 1]} ${state.year}`, Math.round(now.harmonized).toLocaleString(), note));
  }
  return items;
}

function renderTicker() {
  const areas = Object.keys(state.monthly?.areas || {});
  const ordered = areas.includes(state.area) ? [state.area, ...areas.filter((a) => a !== state.area).sort()] : areas.sort();
  const html = ordered.flatMap(areaItems).join('');
  const track = $('ticker');
  // Two copies so the scroll loops seamlessly; replacing children keeps the animation running.
  track.innerHTML = html ? html + html : item('FireCal', 'Loading fire data…');
  $('ticker-date').textContent = state.periods.length ? `${periodLabel(selectedPeriod())}, ${state.year}`.toUpperCase() : 'NASA FIRMS';
}

export function initTicker() {
  const bar = document.querySelector('.ticker');
  $('pause').onclick = () => {
    const paused = bar.classList.toggle('paused');
    $('pause').textContent = paused ? '▶' : 'Ⅱ';
    $('pause').setAttribute('aria-label', paused ? 'Play the activity ticker' : 'Pause the activity ticker');
  };
  onRender(renderTicker);
}
