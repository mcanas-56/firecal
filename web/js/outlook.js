// Outlook mode (US-18): next month's fire outlook and the 2022–2023 back-tests
// from /data/outlook.json (built by src/outlook.py). Labelled as an outlook from fire
// history, not a weather-based forecast. If the file is missing or unavailable, the
// tab shows the reason (main.js) instead of a map.
import { $, state, render } from './state.js';
import { setPoints } from './globe.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
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

function fillMonths(a) {
  const sel = $('outlook-month');
  const keys = ['forecast', ...Object.keys(a.backtest).sort().reverse()];
  if (!keys.includes(state.outlookMonth)) state.outlookMonth = 'forecast';
  const signature = `${state.area}:${keys.join(',')}`;
  if (sel.dataset.signature !== signature) {
    sel.replaceChildren(...keys.map((k) => new Option(
      k === 'forecast' ? `${monthName(a.forecast.month)} · next-month outlook` : `${monthName(k)} · back-test`, k)));
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
    ? `Tested on ${test}: the map ranked fire cells better than the climatology baseline (AUC ${c.auc_model} vs ${c.auc_baseline}).`
    : `The map shows the climatology baseline: on ${test} the model did not beat it.`));
  if (m.error_nowcast !== undefined) {
    parts.push(para(m.ship
      ? `The monthly estimate was off by ${m.error_nowcast}% (median), against ${m.error_baseline}% for the monthly normal.`
      : `The monthly estimate is the monthly normal (off by ${m.error_baseline}% on ${test}).`));
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

export function renderOutlook() {
  const a = areaData();
  fillMonths(a);
  skillNote(a);
  const area = state.area;
  const forecast = state.outlookMonth === 'forecast';
  const view = forecast ? a.forecast : a.backtest[state.outlookMonth];
  const label = monthName(forecast ? a.forecast.month : state.outlookMonth);
  const pts = view.cells.map((c) => [c[0], c[1], c[2], label]);
  setPoints(pts, { kind: 'probability', rings: forecast ? [] : view.fires });

  $('legend-rings').hidden = forecast;
  $('map-label').textContent = `${forecast ? 'OUTLOOK' : 'BACK-TEST'} · ${label.toUpperCase()}`;
  $('outlook-helper').textContent = forecast
    ? `The month after the record ends (${monthName(state.outlook.data_end)}): cells with at least a ${Math.round(state.outlook.min_p * 100)}% chance of a fire cell-day.`
    : `What the tested model expected for ${label}, with the fires that happened as rings.`;

  const t = a.skill.timing;
  const peak = t ? MONTHS[t.peak - 1] : '—';
  const peaks = t ? Object.entries(t.test_peaks).map(([y, mo]) => `${y}: ${MONTHS[mo - 1]}`).join(', ') : '';
  if (forecast) {
    const mo = view.monthly;
    setCard('count', 'Cells on the outlook map', fmt(view.cells.length),
      `${view.cells_30.toLocaleString()} at 30% or more · ${area}`, 'OUTLOOK');
    setCard('window', 'Expected fire cell-days', fmt(mo.expected),
      `Normal ${fmt(mo.normal)} · ${fmt(mo.low)}–${fmt(mo.high)} in past years · ${mo.method === 'nowcast' ? `from ${monthName(mo.last_month)}` : 'monthly normal'}`);
  } else {
    setCard('count', 'Fires on the outlook map', pct(view.on_map_share),
      `${fmt(view.burned_cells)} cells burned · ${fmt(view.new_area_fires)} in new areas`, 'BACK-TEST');
    setCard('window', 'Fire cell-days: expected / actual', `${fmt(view.monthly_predicted)} / ${fmt(view.monthly_actual)}`,
      view.viirs_gap_days ? `VIIRS offline ${view.viirs_gap_days} day${view.viirs_gap_days === 1 ? '' : 's'}: fires undercounted, not scored` : 'Monthly estimate vs the harmonized record');
  }
  setCard('month', 'Typical peak month', peak, peaks ? `Test years · ${peaks}` : '');

  $('map-detail').textContent = `${area} · ${label} · ${pts.length.toLocaleString()} outlook cells`
    + (forecast ? '' : ` · ${view.fires.length.toLocaleString()} fire cells shown as rings`) + ` · ${state.outlook.label}`;
  const empty = $('empty-map');
  empty.hidden = pts.length > 0;
  empty.textContent = `No cell reaches a ${Math.round(state.outlook.min_p * 100)}% chance this month.`;
}

export function initOutlook() {
  $('outlook-month').onchange = () => { state.outlookMonth = $('outlook-month').value; render(); };
}
