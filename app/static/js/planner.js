import { api, completedCourses, courseCode, eligibility, paintBadge } from './api.js';
import { mountTerms } from './terms.js';

const el = id => document.getElementById(id);
const rows = [...document.querySelectorAll('.plan-course')];
const feedback = el('plan-feedback');
const extras = el('extra-courses');
const importDialog = el('import-dialog');
const confirmDialog = el('confirm-dialog');
const name = el('plan-name');
const notes = el('plan-notes');
const template = new Set(rows.map(row => row.dataset.code));
const controls = document.querySelectorAll('.check-row input, .plan-settings input, .plan-settings textarea, .plan-settings button, #extra-form button, #save-plan');
let completed = new Set();
let dirty = false;
let working = false;
let statusRequest;
let statusDelay;

function notify(message, error = false) {
  feedback.textContent = message;
  feedback.classList.toggle('error-text', error);
}

function confirmChange(message, button) {
  el('confirm-message').textContent = message;
  el('confirm-submit').textContent = button;
  confirmDialog.returnValue = 'cancel';
  confirmDialog.showModal();
  return new Promise(resolve => confirmDialog.addEventListener('close', () => {
    resolve(confirmDialog.returnValue === 'apply');
  }, {once: true}));
}

function renderProgress() {
  let count = 0;
  for (const row of rows) {
    const checked = completed.has(row.dataset.code);
    row.querySelector('input').checked = checked;
    if (checked) count++;
  }
  el('planner-progress').textContent = `${count} of ${rows.length}`;
  extras.replaceChildren();
  for (const code of [...completed].filter(code => !template.has(code)).sort()) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button secondary chip';
    button.textContent = `${code} ×`;
    button.setAttribute('aria-label', `Remove ${code} from completed courses`);
    button.addEventListener('click', () => {
      completed.delete(code);
      progressChanged();
      el('extra-code').focus();
    });
    extras.append(button);
  }
}

async function refreshStatus() {
  statusRequest?.abort();
  const request = new AbortController();
  statusRequest = request;
  for (const row of rows) displayStatus(row, completed.has(row.dataset.code)
    ? eligibility(null, completed, row.dataset.code) : {label: 'Checking…', tone: 'neutral'});
  try {
    const status = await api('/api/planner/status', {completed: [...completed]}, {signal: request.signal});
    if (!request.signal.aborted) for (const row of rows) displayStatus(row, eligibility(status, completed, row.dataset.code));
  } catch {
    if (!request.signal.aborted) for (const row of rows) displayStatus(row, eligibility(null, completed, row.dataset.code));
  }
}

function displayStatus(row, state) {
  paintBadge(row.querySelector('.badge'), state);
  row.querySelector('.plan-status small').textContent = state.detail || '';
}

function progressChanged() {
  dirty = true;
  renderProgress();
  invalidateSequence();
  statusRequest?.abort();
  clearTimeout(statusDelay);
  statusDelay = setTimeout(refreshStatus, 200);
}

function populate(plan) {
  name.value = plan?.name || 'My Plan';
  notes.value = plan?.notes || '';
  completed = completedCourses(plan);
  dirty = false;
  renderProgress();
  invalidateSequence();
  refreshStatus();
}

async function doPlanAction(action) {
  if (working) return;
  working = true;
  controls.forEach(control => { control.disabled = true; });
  try { await action(); }
  catch (error) { notify(error.message, true); }
  finally {
    working = false;
    controls.forEach(control => { control.disabled = false; });
  }
}

async function loadPlan() {
  const {plan} = await api('/api/plan/load');
  populate(plan);
  notify(plan ? `Loaded ${plan.name}.` : 'No saved plan yet. Mark the courses you’ve completed and save your progress.');
}

for (const row of rows) row.querySelector('input').addEventListener('change', event => {
  if (event.target.checked) completed.add(row.dataset.code);
  else completed.delete(row.dataset.code);
  progressChanged();
});
for (const field of [name, notes]) field.addEventListener('input', () => { dirty = true; });
el('extra-form').addEventListener('submit', event => {
  event.preventDefault();
  const field = el('extra-code');
  const code = courseCode(field.value);
  if (!code) return notify('Enter a course code such as MATH 110.', true);
  completed.add(code);
  field.value = '';
  progressChanged();
  notify(`Added ${code} to completed courses.`);
});
el('save-plan').addEventListener('click', () => doPlanAction(async () => {
  const {plan} = await api('/api/plan/save', {name: name.value, notes: notes.value, completed: [...completed]});
  name.value = plan.name;
  dirty = false;
  notify(`Saved ${plan.name}.`);
}));
el('load-plan').addEventListener('click', async () => {
  if (!dirty || await confirmChange('Loading replaces unsaved progress on this page.', 'Load latest')) {
    doPlanAction(loadPlan);
  }
});
el('export-plan').addEventListener('click', () => doPlanAction(async () => {
  const data = await api('/api/plan/export');
  const file = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
  const href = URL.createObjectURL(file);
  const link = document.createElement('a');
  link.href = href;
  link.download = 'usask-course-plan.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
  notify('Exported your latest saved progress.');
}));
el('import-plan').addEventListener('click', () => {
  el('import-form').reset();
  el('import-error').hidden = true;
  importDialog.showModal();
});
function importError(message) {
  el('import-error').hidden = false;
  el('import-error').textContent = message;
}
el('plan-file').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 262144) return importError('Choose a JSON file smaller than 256 KB.');
  try {
    el('plan-json').value = await file.text();
    el('import-error').hidden = true;
  } catch { importError('That file could not be read.'); }
});
el('import-form').addEventListener('submit', async event => {
  event.preventDefault();
  const submit = event.submitter;
  if (submit.disabled) return;
  let data;
  try {
    const value = el('plan-json').value;
    if (value.length > 262144) throw new Error();
    data = JSON.parse(value);
    if (!data || Array.isArray(data) || typeof data !== 'object') throw new Error();
  } catch { return importError('Enter a valid plan JSON object under 256 KB.'); }
  submit.disabled = true;
  try {
    const {plan} = await api('/api/plan/import', data);
    importDialog.close();
    populate(plan);
    notify(`Imported ${plan.name}.`);
  } catch (error) { importError(error.message); }
  finally { submit.disabled = false; }
});
el('import-form').addEventListener('input', () => { el('import-error').hidden = true; });

const invalidateSequence = mountTerms({courseCode, confirmChange, getCompleted: () => [...completed]});
doPlanAction(loadPlan);
