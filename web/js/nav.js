// Home / Report a fire navigation, kept in the address (#home, #report).
// Report a fire is a "coming soon" preview: its form is disabled and sends nothing.
import { $ } from './state.js';

function show(page) {
  $('home-page').hidden = page !== 'home';
  $('report-page').hidden = page !== 'report';
  $('home-nav').classList.toggle('active', page === 'home');
  $('report-nav').classList.toggle('active', page === 'report');
  if (page === 'home') document.dispatchEvent(new CustomEvent('firecal:page'));
}

function pageFromHash() { return location.hash === '#report' ? 'report' : 'home'; }

export function navigate(page) {
  if (pageFromHash() !== page) location.hash = page;   // hashchange calls show()
  else show(page);
  window.scrollTo(0, 0);
}

export function initNav() {
  document.querySelectorAll('[data-page]').forEach((el) => { el.onclick = () => navigate(el.dataset.page); });
  window.addEventListener('hashchange', () => show(pageFromHash()));
  $('report-form').onsubmit = (e) => e.preventDefault();   // preview only: nothing is sent
  show(pageFromHash());
}
