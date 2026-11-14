// Predictions mode (US-18, US-18b): from /data/outlook.json (built by src/outlook.py).
// - Typical month (default): how many years since 2012 each cell burned in a calendar
//   month, with the Predictions strip under the globe (normal, range, last year and the
//   next-month prediction per month; click a month to map it).
// - Next month: the model's chance of fire for the month after the record ends.
// - Back-tests: 2022–2023 as the tested model saw it, with the fires that happened.
// Labelled as predictions from fire history, not a weather forecast. If the file is
// missing or unavailable, the tab shows the reason (main.js) instead of a map.
import { $, state, render } from './state.js';
import { setPoints } from './globe.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];
const SVG = 'http://www.w3.org/2000/svg';
const fmt = (n) => (n === null || n === undefined ? '—' : Math.round(n).toLocaleString());
const pct = (x) => (x === null || x === undefined || Number.isNaN(x) ? '—' : `${Math.round(x * 100)}%`);

function monthName(key) {
  const [y, m] = key.split('-').map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

export function outlookReady() {
  return state.outlook?.status === 'ok' && Boolean(state.outlook.areas?.[state.area]);
}

function areaData() { return state.outlook.areas[state.area]; }

// The selection: 'typical-M', 'forecast' or a back-test month 'YYYY-MM'.
function selection(a) {
  const valid = ['forecast', ...Object.keys(a.backtest), ...Object.keys(a.typical).map((m) => `typical-${m}`)];
  if (!valid.includes(state.outlookMonth)) state.outlookMonth = `typical-${a.skill.timing?.peak || 7}`;
  return state.outlookMonth;
}

function fillPicker(a) {
  const sel = $('outlook-month');
  const signature = `${state.area}:${Object.keys(a.backtest).join(',')}`;
  if (sel.dataset.signature !== signature) {
    const [y0, y1] = state.outlook.record_years;
    const group = (label, options) => {
      const g = document.createElement('optgroup');
      g.label = label;
      g.append(...options.map(([value, text]) => new Option(text, value)));
      return g;
    };
    sel.replaceChildren(
      group(`Typical month (${y0}–${y1})`, MONTH_NAMES.map((n, i) => [`typical-${i + 1}`, n])),
      group('Next month', [['forecast', `${monthName(a.forecast.month)} · prediction`]]),
      group('Back-tests', Object.keys(a.backtest).sort().reverse().map((k) => [k, `${monthName(k)} · back-test`])),
    );
    sel.dataset.signature = signature;
  }
  sel.value = state.outlookMonth;
}

function para(text) {
  const p = document.createElement('p');
  p.textContent = text;
  return p;
}

function skillNote(a) {
  const c = a.skill.cell || {};
  const m = a.skill.monthly || {};
  const test = state.outlook.years.test.join('–');
  const months = Object.values(a.backtest);
  const fires = months.reduce((n, b) => n + b.burned_cells, 0);
  const fresh = months.reduce((n, b) => n + b.new_area_fires, 0);
  const strong = document.createElement('strong');
  strong.textContent = state.outlook.label;
  const parts = [strong];
  parts.push(para(c.ship
    ? `Tested on ${test}: the next-month map ranked fire cells better than the historical average (AUC ${c.auc_model} vs ${c.auc_baseline}).`
    : `The next-month map shows the historical average: on ${test} the model did not beat it.`));
  if (m.error_nowcast !== undefined) {
    parts.push(para(m.ship
      ? `Next month's fire cell-days were off by ${m.error_nowcast}% (median), against ${m.error_baseline}% for the monthly normal.`
      : `Next month's estimate is the monthly normal (off by ${m.error_baseline}% on ${test}).`));
  }
  parts.push(para(`It knows fire history, not weather. ${pct(fires ? fresh / fires : null)} of the ${test} fire cells were in places with no fire since 2012, which it cannot foresee.`));
  $('outlook-skill').replaceChildren(...parts);
}

function setCard(n, title, value, note, tag) {
  $(`${n}-title`).textContent = title;
  $(n === 'count' ? 'hotspot-count' : `${n}-stat`).textContent = value;
  $(`${n}-note`).textContent = note;
  if (tag !== undefined) $('count-tag').textContent = tag;
}

function setLegend(title, low, mid, high, rings) {
  $('legend-title').textContent = title;
  $('legend-low').textContent = low;
  $('legend-mid').textContent = mid;
  $('legend-high').textContent = high;
  $('legend-rings').hidden = !rings;
}

// ---- Predictions strip: one column per calendar month ----
function el(tag, attrs, text) {
  const e = document.createElementNS(SVG, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text !== undefined) e.textContent = text;
  return e;
}

function drawStrip(a, activeMonth) {
  // A narrow strip (phones) gets a smaller drawing so its words stay readable.
  const narrow = $('season-chart').clientWidth > 0 && $('season-chart').clientWidth < 500;
  const W = narrow ? 360 : 640, H = narrow ? 110 : 92, top = 6, bottom = narrow ? 20 : 18;
  const h = H - top - bottom, colW = W / 12, fontSize = narrow ? 12 : 10;
  const clim = a.climatology;
  const last = a.last_year.values;
  const f = a.forecast.monthly;
  const nextMonth = Number(a.forecast.month.slice(5));
  const max = Math.max(...clim.map((c) => c.high || 0), ...last.map((v) => v || 0), f.expected || 0) || 1;
  const X = (m) => (m - 0.5) * colW;
  const Y = (v) => top + h - (h * v) / max;
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `Fire cell-days by month in ${state.area}: normal, 2012 to 2023 range, ${a.last_year.year} and next month's prediction` });
  svg.append(el('rect', { x: (activeMonth - 1) * colW + 1, y: 0, width: colW - 2, height: H, rx: 6,
    fill: 'var(--raised)', stroke: 'var(--line)' }));
  let band = '';
  clim.forEach((c, i) => { band += `${i ? 'L' : 'M'}${X(c.month)},${Y(c.high)}`; });
  [...clim].reverse().forEach((c) => { band += `L${X(c.month)},${Y(c.low)}`; });
  svg.append(el('path', { d: `${band}Z`, fill: 'var(--accent)', 'fill-opacity': 0.22, stroke: 'none' }));
  svg.append(el('path', { d: clim.map((c, i) => `${i ? 'L' : 'M'}${X(c.month)},${Y(c.mean)}`).join(''),
    fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2 }));
  last.forEach((v, i) => { if (v !== null) svg.append(el('circle', { cx: X(i + 1), cy: Y(v), r: 2.6, fill: 'var(--orange)' })); });
  if (f.expected !== null) {
    svg.append(el('circle', { cx: X(nextMonth), cy: Y(f.expected), r: 5, fill: 'none',
      stroke: document.documentElement.dataset.theme === 'light' ? '#1f6f9a' : '#8fdcff', 'stroke-width': 2 }));
  }
  clim.forEach((c) => {
    const g = el('g', { class: 'col', tabindex: 0, role: 'button',
      'aria-label': `${MONTH_NAMES[c.month - 1]}: normal ${fmt(c.mean)} fire cell-days, range ${fmt(c.low)} to ${fmt(c.high)}. Show on the globe.` });
    g.append(el('rect', { class: 'hit', x: (c.month - 1) * colW + 1, y: 0, width: colW - 2, height: H, rx: 6, fill: 'transparent' }));
    g.append(el('text', { x: X(c.month), y: H - 5, 'text-anchor': 'middle', 'font-size': fontSize,
      'font-weight': c.month === activeMonth ? 700 : 400, fill: c.month === activeMonth ? 'var(--text)' : 'var(--muted)' },
      narrow ? MONTHS[c.month - 1][0] : MONTHS[c.month - 1]));
    const choose = () => { state.outlookMonth = `typical-${c.month}`; render(); };
    g.addEventListener('click', choose);
    g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(); } });
    svg.append(g);
  });
  $('season-chart').replaceChildren(svg);
  $('season-last-year').textContent = String(a.last_year.year);
  const c = clim.find((x) => x.month === activeMonth);
  $('season-note').textContent = `${MONTHS[activeMonth - 1]}: normal ${fmt(c?.mean)} · range ${fmt(c?.low)}–${fmt(c?.high)}`;
}

// ---- the three views ----
function renderTypical(a, month) {
  const t = a.typical[String(month)];
  const [y0, y1] = state.outlook.record_years;
  const years = y1 - y0 + 1;
  const name = MONTH_NAMES[month - 1];
  const pts = t.cells.map((c) => [c[0], c[1], c[2], `Burned in ${c[3]} of ${years} ${name}s`]);
  setPoints(pts, { kind: 'recurrence' });
  setLegend(`BURNED IN ${name.toUpperCase()}`, `${state.outlook.typical_min_years} of ${years} years`,
    '3–5 years', '6+ years', false);
  $('map-label').textContent = `TYPICAL ${name.toUpperCase()} · ${y0}–${y1}`;
  const routine = state.area === 'Canada' && [4, 5, 10, 11].includes(month)
    ? ' In spring and fall, repeat burning is often agricultural or planned burning; satellites cannot tell it apart from wildfire.' : '';
  $('outlook-helper').textContent = `How many of the ${years} years each cell burned in ${name}. It shows where burning is routine, not where the next fire will start.${routine}`;
  const c = a.climatology.find((x) => x.month === month);
  const lastValue = a.last_year.values[month - 1];
  setCard('count', 'Cells that burn here often', fmt(t.cells_total),
    `In ${state.outlook.typical_min_years}+ of ${years} ${name}s · ${fmt(t.cells_half)} in half or more`, 'TYPICAL');
  setCard('window', `Normal for ${name}`, fmt(c?.mean),
    `Fire cell-days · range ${fmt(c?.low)}–${fmt(c?.high)} · ${a.last_year.year}: ${fmt(lastValue)}`);
  const shown = pts.length < t.cells_total ? ` (the ${fmt(pts.length)} most frequent shown)` : '';
  $('map-detail').textContent = `${state.area} · typical ${name} · ${fmt(t.cells_total)} cells burned in ${state.outlook.typical_min_years}+ years${shown} · ${state.outlook.label}`;
  return pts.length;
}

function renderForecast(a) {
  const view = a.forecast;
  const label = monthName(view.month);
  const pts = view.cells.map((c) => [c[0], c[1], c[2], label]);
  setPoints(pts, { kind: 'probability' });
  setLegend('CHANCE OF FIRE', '5–20%', '20–50%', '50%+', false);
  $('map-label').textContent = `PREDICTION · ${label.toUpperCase()}`;
  $('outlook-helper').textContent = `The month after the record ends (${monthName(state.outlook.data_end)}): cells with at least a ${Math.round(state.outlook.min_p * 100)}% chance of a fire cell-day.`;
  const mo = view.monthly;
  setCard('count', 'Cells on the prediction map', fmt(pts.length),
    `${view.cells_30.toLocaleString()} at 30% or more · ${state.area}`, 'PREDICTION');
  setCard('window', 'Expected fire cell-days', fmt(mo.expected),
    `Normal ${fmt(mo.normal)} · ${fmt(mo.low)}–${fmt(mo.high)} in past years · ${mo.method === 'nowcast' ? `from ${monthName(mo.last_month)}` : 'monthly normal'}`);
  $('map-detail').textContent = `${state.area} · ${label} · ${pts.length.toLocaleString()} cells · ${state.outlook.label}`;
  return pts.length;
}

function renderBacktest(a, key) {
  const view = a.backtest[key];
  const label = monthName(key);
  const pts = view.cells.map((c) => [c[0], c[1], c[2], label]);
  setPoints(pts, { kind: 'probability', rings: view.fires });
  setLegend('CHANCE OF FIRE', '5–20%', '20–50%', '50%+', true);
  $('map-label').textContent = `BACK-TEST · ${label.toUpperCase()}`;
  $('outlook-helper').textContent = `What the tested model expected for ${label}, with the fires that happened as rings.`;
  setCard('count', 'Fires on the prediction map', pct(view.on_map_share),
    `${fmt(view.burned_cells)} cells burned · ${fmt(view.new_area_fires)} in new areas`, 'BACK-TEST');
  setCard('window', 'Fire cell-days: expected / actual', `${fmt(view.monthly_predicted)} / ${fmt(view.monthly_actual)}`,
    view.viirs_gap_days ? `VIIRS offline ${view.viirs_gap_days} day${view.viirs_gap_days === 1 ? '' : 's'}: fires undercounted, not scored` : 'Monthly estimate vs the harmonized record');
  $('map-detail').textContent = `${state.area} · ${label} · ${pts.length.toLocaleString()} cells · ${view.fires.length.toLocaleString()} fire cells shown as rings · ${state.outlook.label}`;
  return pts.length;
}

export function renderOutlook() {
  const a = areaData();
  const key = selection(a);
  fillPicker(a);
  skillNote(a);
  let shown, month;
  if (key.startsWith('typical-')) {
    month = Number(key.slice(8));
    shown = renderTypical(a, month);
  } else if (key === 'forecast') {
    month = Number(a.forecast.month.slice(5));
    shown = renderForecast(a);
  } else {
    month = Number(key.slice(5));
    shown = renderBacktest(a, key);
  }
  drawStrip(a, month);

  const t = a.skill.timing;
  const peaks = t ? Object.entries(t.test_peaks).map(([y, mo]) => `${y}: ${MONTHS[mo - 1]}`).join(', ') : '';
  setCard('month', 'Typical peak month', t ? MONTHS[t.peak - 1] : '—', peaks ? `Test years · ${peaks}` : '');
  const empty = $('empty-map');
  empty.hidden = shown > 0;
  empty.textContent = 'No cells to show for this month.';
}

export function initOutlook() {
  $('outlook-month').onchange = () => { state.outlookMonth = $('outlook-month').value; render(); };
  let wasNarrow = null;   // redraw the strip when the page crosses the phone width
  window.addEventListener('resize', () => {
    const narrow = $('season-chart').clientWidth < 500;
    if (narrow !== wasNarrow && state.mode === 'outlook' && outlookReady()) render();
    wasNarrow = narrow;
  });
}
