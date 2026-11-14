// Fire season (US-05) and the month x year harmonized calendar (US-04), drawn from
// data/monthly.json, which src/web_data.py builds with our harmonization (US-02).
import { $, state, onRender, setYearMonth, stopPlayback } from './state.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
export const COLOURS = ['#34463d', '#91aa64', '#d9c46c', '#e69950', '#d9684c'];
const NAMES = ['No detections', 'Lower', 'Moderate', 'High', 'Very high'];
// Same rule as the daily calendar: quartiles of this area's non-zero months, so both
// calendars read the same way (Lower = bottom quarter of active months ... Very high = top).
export function monthThresholds(values) {
  const v = values.filter((x) => x > 0).sort((a, b) => a - b);
  return [0.25, 0.5, 0.75].map((q) => (v.length ? v[Math.min(v.length - 1, Math.floor((v.length - 1) * q))] : 0));
}

export function monthLevel(v, thresholds) {
  if (v === null || v === undefined) return -1;
  if (v <= 0) return 0;
  return 1 + thresholds.filter((t) => v > t).length;
}

const fmt = (v) => (v === null || v === undefined ? '—' : Math.round(v).toLocaleString());

function renderSeason(info) {
  const s = info?.season;
  const ok = s && (s.status === 'ok' || s.status === 'year_round');
  $('season-start').textContent = ok ? LONG[s.start - 1] : '—';
  $('season-peak').textContent = ok ? LONG[s.peak - 1] : '—';
  $('season-end').textContent = ok ? LONG[s.end - 1] : '—';
  const messages = {
    no_data: 'No data for this area yet.',
    incomplete_data: 'No complete year yet. Missing months are not treated as zero activity.',
    no_activity: 'No fire activity in the complete years, so there is no season to estimate.',
  };
  let note = '';
  if (!s) note = 'Loading…';
  else if (messages[s.status]) note = messages[s.status];
  else {
    note = s.status === 'year_round'
      ? 'Activity stays above the threshold all year: no distinct start or end. '
      : (s.start > s.end ? 'The season crosses December–January. ' : '');
    note += `Consecutive months around the peak with at least ${Math.round(s.threshold * 100)}% of the peak's average harmonized activity, using complete years ${s.years.join(', ')}. A description of past years, not a forecast.`;
  }
  $('season-note').textContent = note;
}

function renderGrid(info) {
  const host = $('month-grid');
  host.replaceChildren();
  if (!info) return;
  const season = new Set(info.season?.months || []);
  const vmax = Math.max(0, ...info.months.map((m) => m.harmonized || 0));
  const thresholds = monthThresholds(info.months.map((m) => m.harmonized));
  const head = document.createElement('div');
  head.className = 'mg-row mg-head';
  head.append(document.createElement('span'));
  MONTHS.forEach((m, i) => {
    const el = document.createElement('span');
    el.textContent = m;
    if (season.has(i + 1)) { el.className = 'in-season'; el.title = 'Part of the estimated fire season'; }
    head.append(el);
  });
  host.append(head);

  const byYear = {};
  for (const m of info.months) (byYear[m.year] ||= {})[m.month] = m;
  for (const year of Object.keys(byYear).map(Number).sort((a, b) => b - a)) {
    const row = document.createElement('div');
    row.className = 'mg-row';
    const label = document.createElement('span');
    label.className = 'mg-year';
    label.textContent = year;
    row.append(label);
    for (let month = 1; month <= 12; month++) {
      const m = byYear[year][month];
      const v = m ? m.harmonized : null;
      const level = monthLevel(v, thresholds);
      const cell = document.createElement('button');
      cell.type = 'button';
      cell.className = 'mg-cell' + (level === -1 ? ' missing' : '') + (level === 0 ? ' zero' : '')
        + (state.year === year && state.calMonth === month - 1 ? ' current' : '');
      cell.dataset.year = year;
      cell.dataset.month = month;
      if (level !== -1) cell.style.background = COLOURS[level];
      const short = v >= 1000 ? (Math.floor(v / 100) / 10).toFixed(1) + 'k' : fmt(v);
      cell.textContent = level > 0 && v >= 0.05 * vmax ? short : '';
      const source = m?.source === 'viirs' ? 'VIIRS' : m?.source === 'modis_scaled' ? 'MODIS × factor' : 'no data';
      const tip = `${MONTHS[month - 1]} ${year}: ${fmt(v)} harmonized fire cell-days`
        + (m ? ` (${source}; VIIRS ${fmt(m.viirs)}, MODIS ${fmt(m.modis)})` : '')
        + (level >= 0 ? ' · ' + NAMES[level] : '');
      cell.title = tip;
      cell.setAttribute('aria-label', tip);
      const known = state.years.includes(year);
      cell.disabled = !known;
      cell.onclick = () => { stopPlayback(); state.scale = 'month'; setYearMonth(year, month - 1); };
      row.append(cell);
    }
    host.append(row);
  }

  const r = (x) => Math.round(x).toLocaleString();
  const legend = [`<span><i class="missing-swatch"></i> No data</span>`, `<span><i style="background:${COLOURS[0]}"></i> 0</span>`,
    `<span><i style="background:${COLOURS[1]}"></i> up to ${r(thresholds[0])}</span>`,
    `<span><i style="background:${COLOURS[2]}"></i> ${r(thresholds[0])}–${r(thresholds[1])}</span>`,
    `<span><i style="background:${COLOURS[3]}"></i> ${r(thresholds[1])}–${r(thresholds[2])}</span>`,
    `<span><i style="background:${COLOURS[4]}"></i> over ${r(thresholds[2])}</span>`];
  $('month-legend').innerHTML = legend.join('');

  const f = info.fit || {};
  $('fit-note').textContent = f.factor
    ? `VIIRS ≈ ${f.factor.toFixed(2)} × MODIS for ${state.area} (R² ${f.r2?.toFixed(2)}, ${f.overlap_months} overlap months). `
      + 'Months with VIIRS use it directly; earlier months use MODIS × factor. Method: docs/harmonization.md.'
    : 'Not enough overlapping MODIS and VIIRS months to fit a factor yet.';
}

function renderMonthly() {
  const info = state.monthly?.areas?.[state.area];
  $('season-area').textContent = state.area;
  renderSeason(info);
  renderGrid(info);
}

export function initMonthly() {
  onRender(renderMonthly);
}
