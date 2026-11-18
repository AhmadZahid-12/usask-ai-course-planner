import { api, courseCode, courseStatus, paintBadge } from './api.js';

const el = id => document.getElementById(id);
const index = JSON.parse(el('course-index').textContent);
const workspace = el('explorer-workspace');
const input = el('course-search');
const results = el('search-results');
const detail = el('course-details');
const title = el('detail-title');
const message = el('lookup-message');
const errorMessage = el('lookup-error');
const compactLayout = matchMedia('(max-width: 930px)');
const cardTemplate = el('course-result');
const verifiedStatus = new Map();
let limit = 12;
let pending;
let selected = '';
let returnTarget;
let resultsScroll = 0;

function markSelection() {
  for (const row of results.querySelectorAll('.search-result')) {
    if (row.dataset.code === selected) row.setAttribute('aria-current', 'true');
    else row.removeAttribute('aria-current');
    const badge = row.querySelector('.badge');
    const state = verifiedStatus.get(row.dataset.code);
    badge.hidden = !state;
    if (state) paintBadge(badge, state);
  }
}

function render() {
  const query = input.value.trim().toLowerCase();
  const compact = query.replace(/[\s-]/g, '').replace(/\.\d+$/, '');
  const level = el('course-level').value;
  const scope = el('course-scope').value;
  const found = index.filter(course =>
    (course.code.toLowerCase().replace(' ', '').includes(compact) ||
      (course.title || '').toLowerCase().includes(query)) &&
    (!level || course.code.split(' ')[1].startsWith(level)) &&
    (!scope || course.starter)
  );
  results.replaceChildren();
  for (const course of found.slice(0, limit)) {
    const row = cardTemplate.content.firstElementChild.cloneNode(true);
    row.dataset.code = course.code;
    row.querySelector('.course-code').textContent = course.code;
    row.querySelector('.course-title').textContent = course.title || 'Title unavailable in index';
    const units = row.querySelector('.course-units');
    units.hidden = course.credit_units == null;
    units.textContent = units.hidden ? '' : `${course.credit_units} cu`;
    row.addEventListener('click', () => lookup(course.code, row));
    results.append(row);
  }
  markSelection();
  el('result-count').textContent = `${found.length} ${found.length === 1 ? 'match' : 'matches'}`;
  if (found.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'inline-message';
    empty.textContent = 'No indexed courses match. Try changing the filters or looking up an exact code.';
    results.append(empty);
  }
  el('more-results').hidden = found.length <= limit;
}

function updateAddress(code) {
  const url = new URL(location.href);
  if (code) url.searchParams.set('q', code);
  else url.searchParams.delete('q');
  url.searchParams.delete('focus');
  history.replaceState(null, '', url);
}

function showResults() {
  pending?.abort();
  pending = undefined;
  workspace.classList.remove('show-course-detail');
  el('detail-content').hidden = true;
  el('detail-content').setAttribute('aria-busy', 'false');
  title.textContent = 'Course details';
  el('detail-code').hidden = true;
  message.textContent = 'Select a result or look up a course by code.';
  message.hidden = false;
  const previous = returnTarget?.matches('.search-result') ?
    [...results.children].find(row => row.dataset.code === selected) : input;
  selected = '';
  markSelection();
  updateAddress('');
  (previous || input).focus({preventScroll: true});
  window.scrollTo(0, resultsScroll);
}

function descriptionWithoutPrerequisites(text, prerequisites) {
  if (!prerequisites) return text;
  const header = /\bpre[- ]?requisite(?:\(s\)|s)?\s*:\s*/i.exec(text);
  if (!header) return text;
  const start = header.index + header[0].length;
  if (!text.startsWith(prerequisites, start)) return text;
  return [text.slice(0, header.index).trim(), text.slice(start + prerequisites.length).trim()].filter(Boolean).join('\n\n');
}

async function lookup(value, trigger) {
  const code = courseCode(value);
  if (!code) {
    errorMessage.textContent = 'Enter an exact code such as CMPT 141 to look up an official entry.';
    errorMessage.hidden = false;
    input.setAttribute('aria-invalid', 'true');
    input.focus();
    return;
  }

  pending?.abort();
  const controller = new AbortController();
  pending = controller;
  if (!workspace.classList.contains('show-course-detail') || !compactLayout.matches) resultsScroll = window.scrollY;
  returnTarget = trigger;
  selected = code;
  markSelection();
  workspace.classList.add('show-course-detail');
  el('detail-content').setAttribute('aria-busy', 'true');
  el('detail-code').textContent = code;
  el('detail-code').hidden = false;
  title.textContent = 'Course details';
  message.textContent = 'Looking up the official course entry…';
  message.classList.remove('feedback-error');
  message.hidden = false;
  el('detail-content').hidden = true;
  el('course-description').open = false;
  if (compactLayout.matches) window.scrollTo(0, 0);
  else if (trigger) detail.scrollIntoView({block: 'nearest'});
  if (trigger || compactLayout.matches) title.focus({preventScroll: true});

  try {
    const data = await api(`/api/catalogue/course?code=${encodeURIComponent(code)}`, undefined, {signal: controller.signal});
    if (controller.signal.aborted) return;
    title.textContent = data.title || data.code;
    el('detail-code').textContent = data.code;
    const reason = data.registration_note || (data.missing.length ? `Missing ${data.missing.join(', ')}` : '');
    const state = courseStatus(data.status, reason);
    verifiedStatus.set(data.code, state);
    markSelection();
    paintBadge(el('detail-status'), state);
    el('detail-credits').textContent = data.credit_units == null ? 'Credit units unavailable' : `${data.credit_units} credit units`;
    el('detail-reason').textContent = reason;
    el('detail-reason').hidden = !reason;
    el('detail-description').textContent = descriptionWithoutPrerequisites(data.description, data.prerequisites) ||
      'The official description could not be loaded. Check the catalogue link.';
    el('detail-prerequisites').textContent = data.prerequisites ||
      (data.available && data.prerequisite_groups !== null
        ? 'No explicit prerequisite was listed in the retrieved description.'
        : 'Check the official entry for the complete requirements.');
    el('detail-source').href = data.source_url;
    el('detail-retrieved').textContent = data.retrieved ? `Retrieved ${data.retrieved}` : (data.cached ? 'Cached description' : '');
    el('detail-assistant').href = `/assistant?code=${encodeURIComponent(data.code)}`;
    updateAddress(data.code);
    el('detail-content').hidden = false;
    message.hidden = true;
  } catch (error) {
    if (controller.signal.aborted) return;
    title.textContent = 'Course details unavailable';
    message.textContent = error.message;
    message.classList.add('feedback-error');
  } finally {
    if (pending === controller) el('detail-content').setAttribute('aria-busy', 'false');
  }
}

for (const field of [input, el('course-level'), el('course-scope')]) field.addEventListener('input', () => {
  limit = 12;
  errorMessage.hidden = true;
  input.removeAttribute('aria-invalid');
  render();
});
el('back-to-results').addEventListener('click', showResults);
detail.addEventListener('keydown', event => {
  if (event.key === 'Escape' && compactLayout.matches) showResults();
});
el('show-more').addEventListener('click', () => {
  const firstNew = limit;
  limit += 12;
  render();
  results.children[firstNew]?.focus();
});
el('lookup-form').addEventListener('submit', event => {
  event.preventDefault();
  const firstMatch = results.querySelector('.search-result');
  if (!courseCode(input.value) && input.value.trim() && firstMatch) firstMatch.focus();
  else lookup(input.value, input);
});
render();
if (courseCode(input.value)) lookup(input.value);
else if (new URLSearchParams(location.search).get('focus') === 'search') input.focus();
