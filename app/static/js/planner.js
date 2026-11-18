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
  const reason = state.detail?.replace(/^Manual verification needed:\s*/i, '') || '';
  row.querySelector('.plan-status small').textContent = reason.charAt(0).toUpperCase() + reason.slice(1);
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
const importForm = el('import-form');
const importText = el('plan-json');
const importFile = el('plan-file');
const importErrorMessage = el('import-error');
const importSubmit = el('submit-import');
const maxImportSize = 256 * 1024;
let fileRead = 0;
let importing = false;

function clearImportError() {
  importErrorMessage.hidden = true;
  importText.removeAttribute('aria-invalid');
  importFile.removeAttribute('aria-invalid');
}

function importError(message, field) {
  importErrorMessage.textContent = message;
  importErrorMessage.hidden = false;
  if (field) {
    field.setAttribute('aria-invalid', 'true');
    field.focus();
  }
}

el('import-plan').addEventListener('click', () => {
  importForm.reset();
  el('plan-file-name').textContent = 'JSON · up to 256 KB';
  clearImportError();
  importDialog.showModal();
});
el('cancel-import').addEventListener('click', () => importDialog.close());
importDialog.addEventListener('cancel', event => {
  if (importing) event.preventDefault();
});
importDialog.addEventListener('close', () => {
  fileRead++;
  if (!importing) importSubmit.disabled = false;
});
importFile.addEventListener('change', async () => {
  const file = importFile.files[0];
  if (!file) return;
  const reading = ++fileRead;
  clearImportError();
  if (file.size > maxImportSize) {
    importSubmit.disabled = false;
    importFile.value = '';
    el('plan-file-name').textContent = 'JSON · up to 256 KB';
    return importError('Choose a JSON file no larger than 256 KB.', importFile);
  }
  importSubmit.disabled = true;
  el('plan-file-name').textContent = `Reading ${file.name}…`;
  try {
    const contents = await file.text();
    if (reading !== fileRead) return;
    importText.value = contents;
    el('plan-file-name').textContent = file.name;
  } catch {
    if (reading !== fileRead) return;
    el('plan-file-name').textContent = 'JSON · up to 256 KB';
    importError('That file could not be read. Try another file or paste the JSON.', importFile);
  } finally {
    if (reading === fileRead) importSubmit.disabled = false;
  }
});
importText.addEventListener('input', clearImportError);
importForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (importSubmit.disabled) return;
  const value = importText.value.trim();
  if (!value) return importError('Choose a plan file or paste the exported JSON.', importText);
  if (new Blob([value]).size > maxImportSize) return importError('Keep the imported JSON under 256 KB.', importText);
  let data;
  try {
    data = JSON.parse(value);
    if (!data || Array.isArray(data) || typeof data !== 'object') throw new Error();
  } catch { return importError('Enter a valid plan JSON object.', importText); }

  importing = true;
  const dismiss = importDialog.querySelectorAll('#cancel-import, button[aria-label="Close import"]');
  dismiss.forEach(button => { button.disabled = true; });
  importSubmit.disabled = true;
  importSubmit.textContent = 'Importing…';
  try {
    const {plan} = await api('/api/plan/import', data);
    populate(plan);
    importDialog.close();
    notify(`Imported ${plan.name}.`);
  } catch (error) { importError(error.message); }
  finally {
    importing = false;
    dismiss.forEach(button => { button.disabled = false; });
    importSubmit.disabled = false;
    importSubmit.textContent = 'Import and load';
  }
});

const invalidateSequence = mountTerms({courseCode, confirmChange, getCompleted: () => [...completed]});
doPlanAction(loadPlan);
