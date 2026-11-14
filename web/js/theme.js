// Dark (default) and light themes. Colours live in CSS variables in styles.css; the
// choice is remembered in localStorage when the browser allows it.
import { $ } from './state.js';

const KEY = 'firecal-theme';

function apply(theme) {
  document.documentElement.dataset.theme = theme;
  const btn = $('theme');
  btn.textContent = theme === 'dark' ? '☼' : '☾';
  btn.setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`);
  document.dispatchEvent(new CustomEvent('firecal:theme'));
}

export function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { /* storage blocked: use the default */ }
  apply(saved === 'light' ? 'light' : 'dark');
  $('theme').onclick = () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    apply(next);
    try { localStorage.setItem(KEY, next); } catch (e) { /* not saved; still switches */ }
  };
}
