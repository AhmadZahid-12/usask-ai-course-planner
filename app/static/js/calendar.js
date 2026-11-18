import {api, courseCode} from './api.js';

const byId = id => document.getElementById(id);
const grid = byId('calendar-grid');
const status = byId('calendar-status');
const zoneInput = byId('calendar-zone');
const editor = byId('calendar-editor');
const editorForm = byId('calendar-event-form');
const editorError = byId('calendar-editor-error');
const confirm = byId('calendar-confirm');
const categories = {
  class: ['Class', '▤'],
  assignment: ['Assignment', '◇'],
  quiz: ['Quiz', '?'],
  exam: ['Exam', '✷'],
  study: ['Study session', '◴'],
  personal: ['Personal', '●'],
};
const dayMs = 86400000;
const zones = new Map();
const linkedCourse = courseCode(new URLSearchParams(location.search).get('course') || '');

function stored(key, fallback) {
  try { return localStorage.getItem(key) || fallback; }
  catch { return fallback; }
}

function remember(key, value) {
  try { localStorage.setItem(key, value); }
  catch { /* The calendar still works when preferences cannot be stored. */ }
}

function validZone(input) {
  if (!/^[A-Za-z][\w+.-]*(\/[\w+.-]+)*$/.test(input)) return '';
  try { return new Intl.DateTimeFormat('en-CA', {timeZone: input}).resolvedOptions().timeZone; }
  catch { return ''; }
}

function zonedLocal(instant, timeZone) {
  if (!zones.has(timeZone)) {
    zones.set(timeZone, new Intl.DateTimeFormat('en-CA', {
      timeZone, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    }));
  }
  const parts = Object.fromEntries(zones.get(timeZone).formatToParts(new Date(instant)).map(part => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function clockOptions(local, timeZone) {
  const naive = Date.parse(`${local}Z`);
  if (!Number.isFinite(naive)) return [];
  // Sample both sides of a possible clock change, then verify each offset against the entered time.
  const offsets = new Set([-dayMs, 0, dayMs].map(delta => {
    const sample = naive + delta;
    return Date.parse(`${zonedLocal(sample, timeZone)}Z`) - sample;
  }));
  return [...offsets].map(offset => naive - offset)
    .filter(instant => zonedLocal(instant, timeZone) === local).sort((a, b) => a - b);
}

function shiftDate(date, days) {
  return new Date(Date.parse(`${date}T00:00:00Z`) + days * dayMs).toISOString().slice(0, 10);
}

function weekday(date) { return new Date(`${date}T00:00:00Z`).getUTCDay(); }
function firstOfWeek(date) { return shiftDate(date, -weekday(date)); }

function shiftMonth(date, direction) {
  const [year, month, day] = date.split('-').map(Number);
  const first = new Date(Date.UTC(year, month - 1 + direction, 1));
  const lastDay = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0)).getUTCDate();
  first.setUTCDate(Math.min(day, lastDay));
  return first.toISOString().slice(0, 10);
}

function displayDate(date, options) {
  return new Intl.DateTimeFormat('en-CA', {...options, timeZone: 'UTC'}).format(new Date(`${date}T00:00:00Z`));
}

const dateLabel = date => displayDate(date, {weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'});
let zone = validZone(stored('planner-calendar-zone', '')) || validZone(Intl.DateTimeFormat().resolvedOptions().timeZone) || 'America/Regina';
let view = 'month';
const currentDate = () => zonedLocal(Date.now(), zone).slice(0, 10);
let selected = currentDate();
let focusDate = selected;
let events = [];
let reminderEvents = [];
let visibleRequest;
let reminderRequest;
let calendarLoaded = false;
let editing;
let trigger;
let busy = false;
let lastReminderDate = currentDate();
const dismissedReminders = new Set();
try {
  for (const key of JSON.parse(stored('planner-calendar-reminders', '[]'))) dismissedReminders.add(key);
} catch { /* Ignore outdated preferences. */ }

function visibleRange() {
  if (view === 'day') return [selected, shiftDate(selected, 1)];
  if (view === 'week') {
    const start = firstOfWeek(selected);
    return [start, shiftDate(start, 7)];
  }
  const first = `${selected.slice(0, 7)}-01`;
  return [firstOfWeek(first), shiftDate(firstOfWeek(first), 42)];
}

function dateSequence(start, end) {
  const dates = [];
  for (let date = start; date < end; date = shiftDate(date, 1)) dates.push(date);
  return dates;
}

function eventDates(event) {
  if (event.all_day) return [event.start, shiftDate(event.end, -1)];
  const end = Date.parse(event.end);
  return [zonedLocal(event.start, zone).slice(0, 10), zonedLocal(end - 1, zone).slice(0, 10)];
}

function groupEvents() {
  const [start, end] = visibleRange();
  const days = new Map(dateSequence(start, end).map(date => [date, []]));
  for (const event of events) {
    const [first, last] = eventDates(event);
    for (const date of dateSequence(first > start ? first : start, last < end ? shiftDate(last, 1) : end)) {
      days.get(date)?.push(event);
    }
  }
  for (const items of days.values()) {
    items.sort((a, b) => Number(b.all_day) - Number(a.all_day) || a.start.localeCompare(b.start) || a.id - b.id);
  }
  return days;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function button(className, text) {
  const node = element('button', className, text);
  node.type = 'button';
  return node;
}

function eventTime(event, day) {
  if (event.all_day) return event.deadline ? 'Due this day' : 'All day';
  const [first, last] = eventDates(event);
  const format = new Intl.DateTimeFormat('en-CA', {timeZone: zone, hour: 'numeric', minute: '2-digit'});
  const start = format.format(new Date(event.start));
  if (event.deadline) return `Due ${start}`;
  const end = format.format(new Date(event.end));
  if (first === last) return `${start}–${end}`;
  if (day === first) return `From ${start}`;
  if (day === last) return `Until ${end}`;
  return 'Continues';
}

function eventButton(event, day, compact = false) {
  const genericDeadline = event.deadline && event.category === 'personal';
  const [category, symbol] = genericDeadline ? ['Deadline', '◇'] : categories[event.category] || categories.personal;
  const node = button('calendar-event');
  node.dataset.category = genericDeadline ? 'assignment' : event.category;
  node.dataset.eventId = event.id;
  const symbolNode = element('span', 'calendar-event-icon', symbol);
  symbolNode.setAttribute('aria-hidden', 'true');
  const copy = element('span', 'calendar-event-copy');
  const title = element('strong', '', event.title);
  copy.append(title);
  const time = eventTime(event, day);
  const context = [time, event.course_code].filter(Boolean).join(' · ');
  if (!compact) copy.append(element('small', '', context));
  node.append(symbolNode, copy);
  node.setAttribute('aria-label', `${event.title}, ${category}, ${context}`);
  if (compact) node.title = `${event.title} · ${context}`;
  node.addEventListener('click', () => openEditor(event, day, node));
  return node;
}

function dateButton(date, count, text) {
  const node = button('calendar-date', text);
  node.dataset.date = date;
  node.tabIndex = date === focusDate ? 0 : -1;
  node.setAttribute('aria-label', `${dateLabel(date)}, ${count} ${count === 1 ? 'event' : 'events'}`);
  node.setAttribute('aria-pressed', String(date === selected));
  if (date === currentDate()) node.setAttribute('aria-current', 'date');
  node.addEventListener('click', event => selectDate(date, event.detail > 0));
  return node;
}

function dayHeader(date, count) {
  const heading = element('h3');
  const label = displayDate(date, {weekday: 'short', month: 'short', day: 'numeric'});
  heading.append(dateButton(date, count, label));
  return heading;
}

function updateAgenda(items) {
  byId('calendar-agenda-title').textContent = displayDate(selected, {weekday: 'short', month: 'short', day: 'numeric'});
  const list = byId('calendar-agenda-list');
  list.replaceChildren(...items.map(event => eventButton(event, selected)));
  if (!items.length) {
    const text = grid.getAttribute('aria-busy') === 'true' ? 'Checking events…' :
      calendarLoaded ? 'No events on this day.' : 'This day could not be checked.';
    list.append(element('p', 'calendar-empty', text));
  }
}

function render() {
  const days = groupEvents();
  grid.replaceChildren();
  if (view === 'month') {
    const weekdays = element('div', 'calendar-weekdays');
    for (const name of ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']) weekdays.append(element('span', '', name));
    const month = element('div', 'calendar-month');
    for (const [date, items] of days) {
      const cell = element('div', 'calendar-cell');
      cell.dataset.selected = String(date === selected);
      cell.dataset.outside = String(date.slice(0, 7) !== selected.slice(0, 7));
      cell.append(dateButton(date, items.length, String(Number(date.slice(8)))));
      const shortcuts = element('div', 'calendar-cell-events');
      for (const event of items.slice(0, 2)) shortcuts.append(eventButton(event, date, true));
      if (items.length > 2) {
        const more = button('calendar-more', `+${items.length - 2} more`);
        more.addEventListener('click', () => {
          selectDate(date);
          byId('calendar-agenda-title').focus();
        });
        shortcuts.append(more);
      }
      const dots = element('div', 'calendar-dots');
      dots.setAttribute('aria-hidden', 'true');
      for (const event of items.slice(0, 3)) {
        const dot = element('span', 'calendar-dot');
        dot.dataset.category = event.category;
        dots.append(dot);
      }
      cell.append(shortcuts, dots);
      month.append(cell);
    }
    grid.append(weekdays, month);
  } else if (view === 'week') {
    const week = element('div', 'calendar-week');
    for (const [date, items] of days) {
      const day = element('section', 'calendar-week-day');
      day.append(dayHeader(date, items.length), ...items.map(event => eventButton(event, date)));
      week.append(day);
    }
    grid.append(week);
  } else {
    const day = element('section', 'calendar-day');
    const items = days.get(selected) || [];
    day.append(dayHeader(selected, items.length), ...items.map(event => eventButton(event, selected)));
    if (!items.length && calendarLoaded && grid.getAttribute('aria-busy') === 'false') {
      day.append(element('p', 'calendar-empty', 'Your day is open.'));
    }
    grid.append(day);
  }
  updateAgenda(days.get(selected) || []);
}

function updateTitle() {
  const options = {month: 'long', year: 'numeric'};
  let title = displayDate(selected, options);
  if (view === 'week') {
    const [start, end] = visibleRange();
    const first = displayDate(start, {month: 'short', day: 'numeric'});
    const last = displayDate(shiftDate(end, -1), {month: 'short', day: 'numeric', year: 'numeric'});
    title = `${first} – ${last}`;
  }
  if (view === 'day') title = displayDate(selected, {...options, day: 'numeric', weekday: 'short'});
  byId('calendar-range-title').textContent = title;
  for (const control of document.querySelectorAll('[data-calendar-view]')) {
    control.setAttribute('aria-pressed', String(control.dataset.calendarView === view));
  }
}

function calendarUrl(start, end) {
  return `/api/calendar/events?${new URLSearchParams({start, end, tz: zone})}`;
}

function feedback(message, failed = false, retry = false) {
  status.classList.toggle('calendar-error', failed);
  status.hidden = !message;
  status.textContent = message;
  if (retry) {
    const action = button('button secondary', 'Try again');
    action.addEventListener('click', () => loadVisible());
    status.append(' ', action);
  }
}

function jumpToDate(date) {
  grid.querySelector(`[data-date="${date}"]`)?.focus();
}

async function loadVisible(restoreDate = '') {
  visibleRequest?.abort();
  const request = new AbortController();
  visibleRequest = request;
  updateTitle();
  grid.setAttribute('aria-busy', 'true');
  feedback('Loading your calendar…');
  render();
  if (restoreDate) jumpToDate(restoreDate);
  const [start, end] = visibleRange();
  try {
    const data = await api(calendarUrl(start, end), undefined, {signal: request.signal});
    if (request.signal.aborted) return;
    events = data.events;
    calendarLoaded = true;
    feedback('');
  } catch (error) {
    if (request.signal.aborted) return;
    calendarLoaded = false;
    feedback(error.message, true, true);
  }
  grid.setAttribute('aria-busy', 'false');
  const active = document.activeElement;
  const activeDate = grid.contains(active) ? active.dataset.date : '';
  const activeEvent = grid.contains(active) ? active.dataset.eventId : '';
  render();
  if (activeDate) jumpToDate(activeDate);
  else if (activeEvent) grid.querySelector(`[data-event-id="${activeEvent}"]`)?.focus();
}

function selectDate(date, pointer = false) {
  const before = visibleRange().join(':');
  selected = date;
  focusDate = date;
  if (before !== visibleRange().join(':')) loadVisible(date);
  else {
    render();
    jumpToDate(date);
  }
  if (pointer && view === 'month' && matchMedia('(max-width: 760px)').matches) {
    byId('calendar-agenda-title').focus();
  }
}

function navigatePeriod(direction) {
  selected = view === 'month' ? shiftMonth(selected, direction) : shiftDate(selected, direction * (view === 'week' ? 7 : 1));
  focusDate = selected;
  loadVisible();
}

grid.addEventListener('keydown', event => {
  const date = event.target.dataset.date;
  if (!date) return;
  const step = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7};
  let target;
  if (event.key in step) target = shiftDate(date, step[event.key]);
  else if (event.key === 'Home') target = firstOfWeek(date);
  else if (event.key === 'End') target = shiftDate(firstOfWeek(date), 6);
  else return;
  event.preventDefault();
  focusDate = target;
  const existing = grid.querySelector(`[data-date="${target}"]`);
  if (existing) {
    event.target.tabIndex = -1;
    existing.tabIndex = 0;
    existing.focus();
  } else {
    selected = target;
    loadVisible(target);
  }
});

for (const control of document.querySelectorAll('[data-calendar-view]')) {
  control.addEventListener('click', () => {
    if (view === control.dataset.calendarView) return;
    view = control.dataset.calendarView;
    focusDate = selected;
    loadVisible();
  });
}
byId('calendar-prev').addEventListener('click', () => navigatePeriod(-1));
byId('calendar-next').addEventListener('click', () => navigatePeriod(1));
byId('calendar-today').addEventListener('click', () => {
  selected = currentDate();
  focusDate = selected;
  loadVisible();
});

function displayReminders() {
  const now = Date.now();
  const due = [];
  for (const event of reminderEvents) {
    if (event.reminder_minutes == null) continue;
    const eventZone = event.timezone || zone;
    const reminderTime = Date.parse(event.reminder_at);
    const end = event.all_day ? clockOptions(`${event.end}T00:00`, eventZone)[0] : Date.parse(event.end);
    const reminderKey = `${event.id}:${event.reminder_at}`;
    if (now >= reminderTime && now <= end && !dismissedReminders.has(reminderKey)) {
      due.push({event, reminderKey});
    }
  }
  byId('calendar-reminders').hidden = !due.length;
  const list = byId('calendar-reminder-list');
  list.replaceChildren();
  for (const {event, reminderKey} of due) {
    const item = element('li');
    const dismiss = button('icon-button', '×');
    dismiss.setAttribute('aria-label', `Dismiss reminder for ${event.title}`);
    dismiss.addEventListener('click', () => {
      dismissedReminders.add(reminderKey);
      remember('planner-calendar-reminders', JSON.stringify([...dismissedReminders].slice(-100)));
      displayReminders();
      (list.querySelector('.icon-button') || byId('calendar-day-add')).focus();
    });
    item.append(eventButton(event, eventDates(event)[0]), dismiss);
    list.append(item);
  }
}

async function loadReminders() {
  reminderRequest?.abort();
  const request = new AbortController();
  reminderRequest = request;
  const today = currentDate();
  lastReminderDate = today;
  try {
    const data = await api(calendarUrl(shiftDate(today, -1), shiftDate(today, 9)), undefined, {signal: request.signal});
    if (request.signal.aborted) return;
    reminderEvents = data.events;
  } catch {
    if (request.signal.aborted) return;
    reminderEvents = [];
  }
  displayReminders();
}

zoneInput.value = zone;
const suggestions = Intl.supportedValuesOf?.('timeZone') || ['America/Regina', 'America/Toronto', 'America/Vancouver', 'America/Edmonton', 'UTC'];
for (const name of new Set(['UTC', zone, ...suggestions])) {
  const item = element('option');
  item.value = name;
  byId('calendar-time-zones').append(item);
}
zoneInput.addEventListener('change', () => {
  const next = validZone(zoneInput.value.trim());
  const message = byId('calendar-zone-status');
  if (!next) {
    zoneInput.setAttribute('aria-invalid', 'true');
    message.textContent = 'Choose a valid region, such as America/Regina.';
    message.hidden = false;
    return;
  }
  zoneInput.removeAttribute('aria-invalid');
  message.hidden = true;
  zone = next;
  zoneInput.value = zone;
  remember('planner-calendar-zone', zone);
  loadVisible();
  loadReminders();
});

function changeInputTypes(allDay) {
  editorForm.elements.start.type = allDay ? 'date' : 'datetime-local';
  editorForm.elements.end.type = allDay ? 'date' : 'datetime-local';
  byId('calendar-end-label').textContent = allDay ? 'Last day' : 'Ends';
}

function formError(message) {
  editorError.textContent = message;
  editorError.hidden = !message;
}

function clearClockChoices() {
  byId('calendar-clock-choices').hidden = true;
  byId('calendar-start-clock').hidden = true;
  byId('calendar-end-clock').hidden = true;
  editorForm.elements.start_clock.value = '';
  editorForm.elements.end_clock.value = '';
}

function defaultStart(date) {
  return date === currentDate() ? zonedLocal(Date.now(), zone) : `${date}T09:00`;
}

function offsetHour(local) {
  return new Date(Date.parse(`${local}Z`) + 3600000).toISOString().slice(0, 16);
}

function openEditor(event, date, origin) {
  if (busy) return;
  editing = event;
  trigger = origin;
  editorForm.reset();
  formError('');
  clearClockChoices();
  const allDay = !!event?.all_day;
  editorForm.elements.all_day.checked = allDay;
  changeInputTypes(allDay);
  editorForm.elements.title.value = event?.title || '';
  editorForm.elements.category.value = event?.category || (linkedCourse ? 'assignment' : 'personal');
  editorForm.elements.course_code.value = event?.course_code || (event ? '' : linkedCourse);
  editorForm.elements.description.value = event?.description || '';
  const reminder = editorForm.elements.reminder_minutes;
  reminder.querySelector('[data-custom]')?.remove();
  if (event?.reminder_minutes != null && ![...reminder.options].some(item => Number(item.value) === event.reminder_minutes && item.value !== '')) {
    const option = element('option', '', `${event.reminder_minutes} minutes before`);
    option.value = event.reminder_minutes;
    option.dataset.custom = 'true';
    reminder.append(option);
  }
  reminder.value = event?.reminder_minutes ?? '';
  const start = event ? (allDay ? event.start : zonedLocal(event.start, zone)) : defaultStart(date);
  const end = event ? (allDay ? shiftDate(event.end, -1) : zonedLocal(event.end, zone)) : offsetHour(start);
  editorForm.elements.start.value = start;
  editorForm.elements.end.value = end;
  byId('calendar-editor-title').textContent = event ? 'Edit event' : 'New event';
  byId('calendar-editor-zone').textContent = `Times shown in ${zone}`;
  byId('calendar-delete').hidden = !event;
  editor.showModal();
}

function closeEditor() {
  if (busy) return;
  editor.close();
  (trigger?.isConnected ? trigger : byId('calendar-new')).focus();
}

editorForm.elements.all_day.addEventListener('change', event => {
  const {start, end} = editorForm.elements;
  const dates = [start.value.slice(0, 10) || selected, end.value.slice(0, 10) || selected];
  changeInputTypes(event.target.checked);
  start.value = event.target.checked ? dates[0] : `${dates[0]}T09:00`;
  end.value = event.target.checked ? dates[1] : `${dates[1]}T10:00`;
  clearClockChoices();
  formError('');
});

for (const name of ['start', 'end']) {
  editorForm.elements[name].addEventListener('input', () => {
    byId(`calendar-${name}-clock`).hidden = true;
    editorForm.elements[`${name}_clock`].value = '';
    byId('calendar-clock-choices').hidden = byId('calendar-start-clock').hidden && byId('calendar-end-clock').hidden;
    formError('');
  });
}

function formInstant(name, values) {
  const local = values[name];
  const before = editing && !editing.all_day ? editing[name] : '';
  if (before && zonedLocal(before, zone) === local) return before;
  const candidates = clockOptions(local, zone);
  if (!candidates.length) throw new Error(`The ${name} time does not occur in ${zone}. Choose another time.`);
  if (candidates.length > 1 && !values[`${name}_clock`]) {
    byId('calendar-clock-choices').hidden = false;
    byId(`calendar-${name}-clock`).hidden = false;
    editorForm.elements[`${name}_clock`].focus();
    throw new Error(`The ${name} time occurs twice in ${zone}. Choose the first or second occurrence.`);
  }
  return new Date(values[`${name}_clock`] === 'last' ? candidates.at(-1) : candidates[0]).toISOString();
}

function toggleBusy(active) {
  busy = active;
  for (const id of ['calendar-save', 'calendar-editor-close', 'calendar-editor-cancel', 'calendar-delete']) {
    byId(id).disabled = active;
  }
  byId('calendar-save').textContent = active ? 'Saving…' : 'Save event';
}

function refetchAfterEdit(message, saved) {
  const origin = trigger;
  editor.close();
  const changed = byId('calendar-change-status');
  changed.textContent = message;
  changed.hidden = false;
  if (saved) {
    [selected] = eventDates(saved);
    focusDate = selected;
  }
  (origin?.isConnected && !origin.dataset.eventId ? origin : byId('calendar-new')).focus();
  loadVisible();
  loadReminders();
}

editorForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const {start_clock, end_clock, ...values} = Object.fromEntries(new FormData(editorForm));
  formError('');
  try {
    const allDay = !!values.all_day;
    const code = values.course_code.trim();
    if (code && !courseCode(code)) throw new Error('Enter a course code such as CMPT 141.');
    const start = allDay ? values.start : formInstant('start', {...values, start_clock});
    const end = allDay ? shiftDate(values.end, 1) : formInstant('end', {...values, end_clock});
    if (allDay ? end <= start : Date.parse(end) <= Date.parse(start)) throw new Error('End the event after it starts.');
    const payload = {
      ...values, start, end, course_code: code ? courseCode(code) : '', all_day: allDay,
      timezone: editing?.timezone || zone, reminder_minutes: values.reminder_minutes === '' ? null : Number(values.reminder_minutes),
    };
    toggleBusy(true);
    const result = editing ? await api(`/api/calendar/events/${editing.id}`, undefined, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    }) : await api('/api/calendar/events', payload);
    refetchAfterEdit('Event saved.', result.event);
  } catch (error) {
    formError(error.message);
  } finally {
    toggleBusy(false);
  }
});

byId('calendar-delete').addEventListener('click', () => {
  byId('calendar-confirm-detail').textContent = `Delete “${editing.title}” from your calendar?`;
  editor.close();
  confirm.returnValue = 'cancel';
  confirm.showModal();
});

confirm.addEventListener('close', async () => {
  if (confirm.returnValue !== 'delete') {
    editor.showModal();
    byId('calendar-delete').focus();
    return;
  }
  toggleBusy(true);
  try {
    const response = await fetch(`/api/calendar/events/${editing.id}`, {method: 'DELETE'});
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new Error(data?.error || 'The event could not be deleted.');
    }
    refetchAfterEdit('Event deleted.');
  } catch (error) {
    editor.showModal();
    formError(error.message);
  } finally {
    toggleBusy(false);
  }
});

byId('calendar-editor-cancel').addEventListener('click', closeEditor);
byId('calendar-editor-close').addEventListener('click', closeEditor);
editor.addEventListener('cancel', event => {
  event.preventDefault();
  closeEditor();
});
byId('calendar-new').addEventListener('click', event => openEditor(null, selected, event.currentTarget));
byId('calendar-day-add').addEventListener('click', event => openEditor(null, selected, event.currentTarget));
document.addEventListener('keydown', event => {
  if (event.key.toLowerCase() !== 'n' || event.metaKey || event.ctrlKey || event.altKey ||
      event.target.closest('input,textarea,select,[contenteditable]') || document.querySelector('dialog[open]')) return;
  event.preventDefault();
  openEditor(null, selected, byId('calendar-new'));
});

loadVisible();
loadReminders();
setInterval(() => {
  if (lastReminderDate !== currentDate() || !calendarLoaded) return loadReminders();
  displayReminders();
}, 60000);
