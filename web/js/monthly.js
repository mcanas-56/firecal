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
  const host = $('season-curve');
  host.replaceChildren();
  const yearControl = $('curve-year');
  const years = [...new Set((info?.months || []).map(m => m.year))].sort((a,b) => b-a);
  yearControl.replaceChildren(...years.map(y => new Option(String(y), String(y))));
  yearControl.value = state.year;
  if (!info || !window.d3 || !years.length) return;
  const d3 = window.d3;
  const valid = v => typeof v === 'number' && Number.isFinite(v) && v >= 0;
  const byYear = new Map(years.map(y => [y, info.months.filter(m => m.year === y)]));
  const complete = years.filter(y => byYear.get(y).length === 12 && byYear.get(y).every(m => valid(m.harmonized)));
  const selected = Array.from({length:12}, (_,i) => {
    const m = info.months.find(m => m.year === state.year && m.month === i+1);
    return {month:i+1,value:valid(m?.harmonized) ? m.harmonized : null};
  });
  const average = selected.map(({month}) => ({month,value:complete.length ? d3.mean(complete, y => byYear.get(y).find(m => m.month === month).harmonized) : null}));
  // A shared domain across the area's entire record keeps year comparisons stable.
  const max = d3.max(info.months.filter(m => valid(m.harmonized)), m => m.harmonized) || 1;
  const x = d3.scaleLinear().domain([1,12]).range([62,772]);
  const y = d3.scaleLinear().domain([0,max*1.12]).nice(4).range([264,26]);
  const svg = d3.select(host).append('svg').attr('viewBox','0 0 800 305').attr('role','img').attr('aria-label',`Monthly harmonized fire activity for ${state.area}, ${state.year}, compared with the mean across ${complete.length} complete years. Missing values are gaps.`);
  svg.append('title').text(`Seasonal activity in ${state.area}: ${state.year} and historical average`);
  const season = new Set(info.season?.months || []);
  svg.append('g').selectAll('rect').data(selected.filter(d=>season.has(d.month))).join('rect').attr('x',d=>Math.max(62,x(d.month)-32)).attr('width',d=>Math.min(772,x(d.month)+32)-Math.max(62,x(d.month)-32)).attr('y',26).attr('height',238).attr('class','curve-season-band');
  svg.append('g').attr('class','curve-y-axis').attr('transform','translate(62,0)').call(d3.axisLeft(y).ticks(4).tickSize(-710).tickFormat(d3.format('~s'))).call(g=>g.select('.domain').remove());
  svg.append('g').attr('class','curve-x-axis').attr('transform','translate(0,264)').call(d3.axisBottom(x).tickValues(d3.range(1,13)).tickFormat(m=>MONTHS[m-1]).tickSize(0).tickPadding(18)).call(g=>g.select('.domain').remove());
  const line = d3.line().defined(d=>d.value!==null).x(d=>x(d.month)).y(d=>y(d.value));
  svg.append('path').datum(selected).attr('class','curve-area').attr('d',d3.area().defined(d=>d.value!==null).x(d=>x(d.month)).y0(y(0)).y1(d=>y(d.value)));
  svg.append('path').datum(average).attr('class','curve-average').attr('d',line);
  svg.append('path').datum(selected).attr('class','curve-selected').attr('d',line);
  function describe(d) {
    const mean = average[d.month-1].value;
    $('month-detail').textContent = `${LONG[d.month-1]} ${state.year} · ${fmt(d.value)} fire cell-days`+(mean!==null?` · Historical average: ${fmt(mean)}`:'');
  }
  function open(d){stopPlayback();state.scale='month';setYearMonth(state.year,d.month-1);}
  svg.append('g').selectAll('circle').data(selected.filter(d=>d.value!==null)).join('circle').attr('cx',d=>x(d.month)).attr('cy',d=>y(d.value)).attr('r',6).attr('class',d=>'curve-point'+(d.month===state.calMonth+1?' is-current':'')).attr('tabindex',0).attr('role','button').attr('aria-label',d=>`${LONG[d.month-1]} ${state.year}: ${fmt(d.value)} harmonized fire cell-days. Open this month.`).on('pointerenter',(_,d)=>describe(d)).on('focus',(_,d)=>describe(d)).on('click',(_,d)=>open(d)).on('keydown',(event,d)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open(d)}}).append('title').text(d=>`${LONG[d.month-1]}: ${fmt(d.value)} fire cell-days`);
  const active = selected.find(d=>d.month===state.calMonth+1);
  describe(active);
  const peak = selected.reduce((best,d)=>d.value!==null&&(!best||d.value>best.value)?d:best,null);
  $('curve-peak').textContent = peak&&peak.value>0?`Busiest month in ${state.year}: ${LONG[peak.month-1]} · ${fmt(peak.value)} fire cell-days`: 'No positive activity recorded for this year.';
  $('curve-average-label').textContent=complete.length?`Historical average · ${Math.min(...complete)}–${Math.max(...complete)} (${complete.length} complete years)`:'Historical average unavailable';
  const f=info.fit||{};
  $('fit-note').textContent=f.factor?`VIIRS ≈ ${f.factor.toFixed(2)} × MODIS for ${state.area}. The record uses VIIRS where available and scaled MODIS otherwise. See docs/harmonization.md.`:'Not enough overlap to fit a harmonization factor.';
}

function renderMonthly() {
  const info = state.monthly?.areas?.[state.area];
  $('season-area').textContent = state.area;
  renderSeason(info);
  renderGrid(info);
}

export function initMonthly() {
  $('curve-year').onchange = () => { stopPlayback(); setYearMonth(Number($('curve-year').value), state.calMonth); };
  onRender(renderMonthly);
}
