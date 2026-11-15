// Home navigation. Retired page links return to the main view.
import { $ } from './state.js';

function showHome() {
  $('home-page').hidden = false;
  $('home-nav').classList.add('active');
  if (location.hash && location.hash !== '#home') {
    history.replaceState(null, '', location.pathname + location.search + '#home');
  }
  document.dispatchEvent(new CustomEvent('firecal:page'));
}

export function navigate() {
  showHome();
  window.scrollTo(0, 0);
}

export function initNav() {
  document.querySelectorAll('[data-page="home"]').forEach(el => { el.onclick = navigate; });
  window.addEventListener('hashchange', showHome);
  showHome();
}
