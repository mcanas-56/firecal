// Day / week / month timeline: scale switch above a slider spanning the selected year,
// a play button that animates through it, and the date field with Previous / Next.
import { $, state, onRender, selectedPeriod, periodLabel, setDate, setScale, stopPlayback } from './state.js';

const PLAY_MS = 1200;

function step(n) {
  const i = state.periods.indexOf(selectedPeriod());
  const next = Math.max(0, Math.min(state.periods.length - 1, i + n));
  setDate(state.periods[next].start);
}

function renderTimeline() {
  const p = selectedPeriod();
  const i = state.periods.indexOf(p);
  document.querySelectorAll('.scale-option').forEach((btn) => {
    const active = btn.dataset.scale === state.scale;
    btn.classList.toggle('selected', active);
    btn.setAttribute('aria-pressed', String(active));
  });
  const slider = $('date-slider');
  slider.max = String(state.periods.length - 1);
  slider.value = String(i);
  $('slider-date').textContent = periodLabel(p) + ', ' + state.year;
  $('timeline-foot').textContent = state.year + ' archive · Choose days, weeks or months';

  const field = $('map-date');
  field.min = state.year + '-01-01';
  field.max = state.year + '-12-31';
  field.value = state.date;
  $('prev-date').disabled = i === 0;
  $('next-date').disabled = i === state.periods.length - 1;
}

export function initTimeline() {
  document.querySelectorAll('.scale-option').forEach((btn) => {
    btn.onclick = () => { stopPlayback(); setScale(btn.dataset.scale); };
  });
  $('date-slider').oninput = () => setDate(state.periods[Number($('date-slider').value)].start);
  $('play-dates').onclick = () => {
    if (state.playTimer) { stopPlayback(); return; }
    $('play-dates').textContent = 'Ⅱ';
    $('play-dates').setAttribute('aria-label', 'Pause');
    state.playTimer = setInterval(() => {
      const next = (state.periods.indexOf(selectedPeriod()) + 1) % state.periods.length;
      setDate(state.periods[next].start);
    }, PLAY_MS);
  };
  $('map-date').onchange = () => { stopPlayback(); setDate($('map-date').value); };
  $('prev-date').onclick = () => { stopPlayback(); step(-1); };
  $('next-date').onclick = () => { stopPlayback(); step(1); };
  onRender(renderTimeline);
}
