import { api, completedCourses, eligibility, paintBadge } from './api.js';

const element = id => document.getElementById(id);
const list = element('dashboard-courses');
const rows = [...list.querySelectorAll('[data-code]')];
const message = element('dashboard-message');
const retry = element('check-status');

async function refresh() {
  retry.hidden = true;
  message.hidden = false;
  list.setAttribute('aria-busy', 'true');
  message.textContent = 'Checking your saved plan and catalogue prerequisites…';
  let completed = new Set();
  let planLoaded = false;
  try {
    const { plan } = await api('/api/plan/load');
    planLoaded = true;
    completed = completedCourses(plan);
    const count = rows.filter(row => completed.has(row.dataset.code)).length;
    const percent = rows.length ? Math.round(count / rows.length * 100) : 0;
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
    const rank = {eligible: 0, review: 1, locked: 2, complete: 3, neutral: 4};
    const ranked = rows.map(row => {
      const state = eligibility(status, completed, row.dataset.code);
      paintBadge(row.querySelector('.row-status'), state);
      if (state.detail) row.querySelector('.course-entry').setAttribute('aria-description', state.detail);
      return {row, order: rank[state.tone]};
    });
    // Keep focus on a course if someone reaches the list before its status loads.
    if (!list.contains(document.activeElement)) {
      list.append(...ranked.sort((left, right) => left.order - right.order).map(item => item.row));
    }
    message.hidden = true;
  } catch {
    for (const row of rows) paintBadge(row.querySelector('.row-status'), eligibility(null, completed, row.dataset.code));
    if (!planLoaded) element('template-count').textContent = 'Saved progress unavailable';
    message.textContent = planLoaded ? 'Course status is temporarily unavailable.' : 'Your saved plan could not be loaded.';
    retry.hidden = false;
  } finally {
    list.setAttribute('aria-busy', 'false');
  }
}

retry.addEventListener('click', refresh);
refresh();
