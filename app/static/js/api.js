export async function api(path, body, options = {}) {
  const response = await fetch(path, {
    ...options,
    ...(body === undefined ? {} : {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(data?.error || 'Could not reach the planner. Please try again.');
  return data;
}

export function courseCode(value) {
  const match = value.trim().toUpperCase().match(/^([A-Z]{2,5})[\s-]*(\d{2,4}[A-Z]?)(?:\.\d+)?$/);
  return match ? `${match[1]} ${match[2]}` : '';
}

export function completedCourses(plan) {
  try {
    const courses = JSON.parse(plan?.completed_json || '[]');
    return new Set(Array.isArray(courses) ? courses.filter(code => typeof code === 'string').map(code => courseCode(code) || code) : []);
  } catch { return new Set(); }
}

const statuses = {
  completed: {label: 'Completed', tone: 'complete'},
  eligible: {label: 'Prerequisites met', tone: 'eligible'},
  locked: {label: 'Locked', tone: 'locked'},
  review: {label: 'Manual verification needed', tone: 'review'},
  unavailable: {label: 'Status unavailable', tone: 'neutral'},
};

export function courseStatus(status, detail) {
  return {...(statuses[status] || statuses.unavailable), detail};
}

export function eligibility(status, completed, code) {
  if (completed.has(code)) return courseStatus('completed');
  if (status?.unlocked.includes(code)) return courseStatus('eligible');
  const locked = status?.locked.find(item => item.code === code);
  if (locked?.reason) return courseStatus('review', locked.reason);
  if (locked) return courseStatus('locked', `Missing ${locked.missing_prereqs.join(', ')}`);
  return courseStatus('unavailable');
}

export function paintBadge(badge, state) {
  badge.classList.remove('complete', 'eligible', 'locked', 'review', 'neutral');
  badge.classList.add(state.tone);
  badge.textContent = state.label;
  if (state.detail) badge.title = state.detail;
  else badge.removeAttribute('title');
}
