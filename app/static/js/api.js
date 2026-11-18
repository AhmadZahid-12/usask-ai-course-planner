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

export function completedCourses(plan) {
  try {
    const courses = JSON.parse(plan?.completed_json || '[]');
    return new Set(Array.isArray(courses) ? courses.filter(code => typeof code === 'string') : []);
  } catch { return new Set(); }
}

export function eligibility(status, completed, code) {
  if (completed.has(code)) return { label: 'Completed', tone: 'complete' };
  if (status?.unlocked.includes(code)) return { label: 'Prerequisites met', tone: 'eligible' };
  const locked = status?.locked.find(item => item.code === code);
  if (locked?.reason) return { label: 'Manual verification needed', tone: 'review', detail: locked.reason };
  if (locked) return { label: 'Locked', tone: 'locked', detail: `Missing ${locked.missing_prereqs.join(', ')}` };
  return { label: 'Status unavailable', tone: 'neutral' };
}

export function paintBadge(badge, state) {
  badge.className = `badge ${state.tone}`;
  badge.textContent = state.label;
  if (state.detail) badge.title = state.detail;
  else badge.removeAttribute('title');
}
