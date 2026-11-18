const root = document.documentElement;
const system = matchMedia('(prefers-color-scheme: light)');
const mobile = matchMedia('(max-width: 760px)');
const navigation = document.querySelector('#mobile-navigation');
const sidebar = document.querySelector('#sidebar-toggle');
const themeSelect = document.querySelector('#theme-select');

function getPreference(key, fallback) {
  try { return localStorage.getItem(key) || fallback; } catch { return fallback; }
}

function setPreference(key, value) {
  try { localStorage.setItem(key, value); } catch {}
}

let theme = getPreference('planner-theme', 'dark');
function applyTheme() {
  root.dataset.theme = theme === 'system' ? (system.matches ? 'light' : 'dark') : theme;
  if (themeSelect) themeSelect.value = theme;
}
function changeTheme(value) {
  theme = value;
  setPreference('planner-theme', value);
  applyTheme();
}

sidebar.addEventListener('click', () => {
  if (mobile.matches) {
    navigation.showModal();
    return;
  }
  const state = root.dataset.sidebar === 'collapsed' ? 'expanded' : 'collapsed';
  root.dataset.sidebar = state;
  setPreference('planner-sidebar', state);
  updateNavigation();
});

function updateNavigation() {
  sidebar.setAttribute('aria-controls', mobile.matches ? 'mobile-navigation' : 'desktop-sidebar');
  sidebar.setAttribute('aria-expanded', String(mobile.matches ? navigation.open : root.dataset.sidebar !== 'collapsed'));
}

navigation.addEventListener('close', updateNavigation);
sidebar.addEventListener('click', updateNavigation);
mobile.addEventListener('change', () => {
  if (navigation.open && !mobile.matches) navigation.close();
  updateNavigation();
});
document.querySelector('#theme-toggle').addEventListener('click', () => {
  changeTheme(root.dataset.theme === 'dark' ? 'light' : 'dark');
});
themeSelect?.addEventListener('change', () => changeTheme(themeSelect.value));
system.addEventListener('change', applyTheme);
document.addEventListener('keydown', event => {
  if (event.key !== '/' || event.altKey || event.ctrlKey || event.metaKey ||
      event.target.closest('input, textarea, select, [contenteditable]') || document.querySelector('dialog[open]')) return;
  event.preventDefault();
  if (document.querySelector('#course-search')) document.querySelector('#course-search').focus();
  else location.assign(document.querySelector('.header-search').href);
});

applyTheme();
updateNavigation();
