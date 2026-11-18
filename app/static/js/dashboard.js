import { api, completedCourses, eligibility, paintBadge } from './api.js';

const element = id => document.getElementById(id);
const rows = [...document.querySelectorAll('[data-code]')];
const message = element('dashboard-message');
const retry = element('check-status');

async function refresh() {
  retry.hidden = true;
  message.hidden = false;
  element('dashboard-courses').setAttribute('aria-busy', 'true');
  message.textContent = 'Checking your saved plan and catalogue prerequisites…';
  let completed = new Set();
  let planLoaded = false;
  try {
    const { plan } = await api('/api/plan/load');
    planLoaded = true;
    completed = completedCourses(plan);
    const count = rows.filter(row => completed.has(row.dataset.code)).length;
    const percent = rows.length ? Math.round(count / rows.length * 100) : 0;
    element('completed-count').textContent = count;
    element('template-percent').textContent = `${percent}%`;
    element('template-progress').value = percent;
    element('template-count').textContent = `${count} of ${rows.length} courses completed`;
    if (rows.length && rows.every(row => Number(row.dataset.credit) > 0)) {
      const total = rows.reduce((sum, row) => sum + Number(row.dataset.credit), 0);
      const earned = rows.reduce((sum, row) => sum + (completed.has(row.dataset.code) ? Number(row.dataset.credit) : 0), 0);
      element('template-credits').textContent = `${earned} of ${total} starter credit units`;
    }
    const status = await api('/api/planner/status', { completed: [...completed] });
    element('eligible-count').textContent = status.unlocked.length;
    element('locked-count').textContent = status.locked.filter(item => !item.reason).length;
    element('review-count').textContent = status.locked.filter(item => item.reason).length;
    for (const row of rows) paintBadge(row.querySelector('.row-status'), eligibility(status, completed, row.dataset.code));
    message.hidden = true;
  } catch {
    for (const row of rows) paintBadge(row.querySelector('.row-status'), eligibility(null, completed, row.dataset.code));
    message.textContent = planLoaded ? 'Course status is temporarily unavailable.' : 'Your saved plan could not be loaded.';
    retry.hidden = false;
  } finally {
    element('dashboard-courses').setAttribute('aria-busy', 'false');
  }
}

retry.addEventListener('click', refresh);
refresh();
