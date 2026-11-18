import { api, courseCode, paintBadge } from './api.js';

const el = id => document.getElementById(id);
const index = JSON.parse(el('course-index').textContent);
const input = el('course-search');
const results = el('search-results');
const detail = el('course-details');
const message = el('lookup-message');
const labels = { completed: 'Completed', eligible: 'Prerequisites met', locked: 'Locked', review: 'Manual verification needed' };
let limit = 12;
let pending;

function render() {
  const query = input.value.trim().toLowerCase();
  const compact = query.replace(/[\s-]/g, '').replace(/\.\d+$/, '');
  const found = index.filter(course =>
    (course.code.toLowerCase().replace(' ', '').includes(compact) ||
      (course.title || '').toLowerCase().includes(query)) &&
    (!el('course-level').value || course.code.split(' ')[1].startsWith(el('course-level').value)) &&
    (!el('course-scope').value || course.starter)
  );
  results.replaceChildren();
  for (const course of found.slice(0, limit)) {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'course-row search-result';
    const code = document.createElement('span');
    code.className = 'course-code';
    code.textContent = course.code;
    const title = document.createElement('strong');
    title.textContent = course.title || 'Title unavailable in index';
    const units = document.createElement('small');
    units.className = 'muted';
    units.textContent = course.credit_units !== null ? `${course.credit_units} cu` : '—';
    row.append(code, title, units);
    row.addEventListener('click', () => lookup(course.code, true));
    results.append(row);
  }
  el('result-count').textContent = `${found.length} ${found.length === 1 ? 'match' : 'matches'}`;
  if (found.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'inline-message';
    empty.textContent = 'No indexed courses match. Try changing the filters or looking up an exact code.';
    results.append(empty);
  }
  el('more-results').hidden = found.length <= limit;
}

async function lookup(value, focus) {
  pending?.abort();
  const code = courseCode(value);
  if (!code) {
    message.hidden = false;
    el('detail-content').hidden = true;
    detail.setAttribute('aria-busy', 'false');
    el('detail-title').textContent = 'Course details';
    el('detail-code').textContent = '';
    message.textContent = 'Enter an exact course code such as CMPT 141 to look up the official entry.';
    return;
  }
  const controller = new AbortController();
  pending = controller;
  detail.setAttribute('aria-busy', 'true');
  el('detail-title').textContent = 'Checking catalogue…';
  el('detail-code').textContent = '';
  message.textContent = 'Looking up the official course entry…';
  message.hidden = false;
  el('detail-content').hidden = true;
  if (focus) detail.scrollIntoView({block: 'nearest'});
  try {
    const data = await api(`/api/catalogue/course?code=${encodeURIComponent(code)}`, undefined, { signal: controller.signal });
    if (controller.signal.aborted) return;
    el('detail-title').textContent = data.title || data.code;
    el('detail-code').textContent = data.code;
    paintBadge(el('detail-status'), { label: labels[data.status], tone: data.status });
    el('detail-credits').textContent = data.credit_units === null ? 'Credit units unavailable' :
      `${data.credit_units} credit units`;
    const reason = el('detail-reason');
    reason.textContent = data.registration_note || (data.missing.length ? `Missing ${data.missing.join(', ')}` : '');
    reason.hidden = !reason.textContent;
    el('detail-description').textContent = data.description || 'The official description could not be loaded. Check the catalogue link.';
    el('detail-prerequisites').textContent = data.prerequisites ||
      (data.available && data.prerequisite_groups !== null
        ? 'No explicit prerequisite was listed in the retrieved description.'
        : 'Check the official entry for the complete requirements.');
    el('detail-source').href = data.source_url;
    el('detail-retrieved').textContent = data.retrieved ? ` · Retrieved ${data.retrieved}` : (data.cached ? ' · Cached description' : '');
    el('detail-assistant').href = `/assistant?code=${encodeURIComponent(data.code)}`;
    const page = new URL(location.href);
    page.searchParams.set('q', data.code);
    page.searchParams.delete('focus');
    history.replaceState(null, '', page);
    el('detail-content').hidden = false;
    message.hidden = true;
    if (focus) el('detail-title').focus({preventScroll: true});
  } catch (error) {
    if (controller.signal.aborted) return;
    el('detail-title').textContent = 'Course details unavailable';
    message.textContent = error.message;
  } finally {
    if (pending === controller) detail.setAttribute('aria-busy', 'false');
  }
}

for (const field of [input, el('course-level'), el('course-scope')]) field.addEventListener('input', () => {
  limit = 12;
  render();
});
el('show-more').addEventListener('click', () => {
  const firstNew = limit;
  limit += 12;
  render();
  results.children[firstNew]?.focus();
});
el('lookup-form').addEventListener('submit', event => {
  event.preventDefault();
  lookup(input.value, true);
});
render();
if (input.value) lookup(input.value, false);
else if (new URLSearchParams(location.search).get('focus') === 'search') input.focus();
