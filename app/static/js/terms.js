import { api } from './api.js';

const key = 'usask-semester-draft-v1';
const el = id => document.getElementById(id);

export function mountTerms({courseCode, confirmChange, getCompleted}) {
  const list = el('terms');
  const message = el('sequence-message');
  const check = el('check-sequence');
  const instructions = message.textContent;
  let terms = [];
  let checks = [];
  let request;
  try {
    const saved = JSON.parse(localStorage.getItem(key) || '[]');
    if (Array.isArray(saved)) terms = saved.filter(term =>
      typeof term?.name === 'string' && Array.isArray(term.courses) &&
      term.courses.every(code => typeof code === 'string'));
  } catch {}

  function invalidate() {
    request?.abort();
    check.disabled = false;
    checks = [];
    list.querySelectorAll('.sequence-result').forEach(element => element.remove());
    message.textContent = instructions;
  }

  function update() {
    invalidate();
    try { localStorage.setItem(key, JSON.stringify(terms)); }
    catch { message.textContent = 'Browser storage is unavailable. This draft will be lost when you leave this page.'; }
    render();
  }

  function checkResult(code, index) {
    const result = checks[index]?.find(item => item.course === code);
    if (!result) return null;
    const label = document.createElement('small');
    label.className = 'sequence-result';
    const dependencies = result.dependencies.map(group => group.join(' + ')).join(' or ');
    if (result.already_completed) label.textContent = 'Already marked complete';
    else if (result.reason) label.textContent = result.reason;
    else if (result.missing.length) label.textContent = `Missing before this term: ${result.missing.join(', ')}`;
    else label.textContent = 'Prerequisites in sequence';
    if (dependencies && !result.already_completed) {
      label.append(document.createElement('br'), `Prerequisites shown: ${dependencies}`);
    }
    return label;
  }

  function render() {
    list.replaceChildren();
    for (const [index, term] of terms.entries()) {
      const box = document.createElement('section');
      box.className = 'term';
      const header = document.createElement('header');
      const title = document.createElement('h3');
      title.textContent = term.name;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'button secondary danger';
      remove.textContent = 'Remove term';
      remove.addEventListener('click', async () => {
        if (term.courses.length && !await confirmChange(`Remove ${term.name} and its draft courses?`, 'Remove term')) return;
        terms.splice(index, 1);
        update();
        el('term-name').focus();
      });
      header.append(title, remove);
      box.append(header);
      for (const code of term.courses) {
        const row = document.createElement('div');
        row.className = 'term-course';
        const course = document.createElement('a');
        course.className = 'course-code';
        course.href = `/courses?q=${encodeURIComponent(code)}`;
        course.textContent = code;
        const deleteCourse = document.createElement('button');
        deleteCourse.type = 'button';
        deleteCourse.className = 'icon-button';
        deleteCourse.textContent = '×';
        deleteCourse.setAttribute('aria-label', `Remove ${code} from ${term.name}`);
        deleteCourse.addEventListener('click', () => {
          term.courses = term.courses.filter(value => value !== code);
          update();
          list.children[index]?.querySelector('input').focus();
        });
        row.append(course, deleteCourse);
        const result = checkResult(code, index);
        if (result) row.append(result);
        box.append(row);
      }
      const form = document.createElement('form');
      form.className = 'inline-form';
      const field = document.createElement('input');
      field.required = true;
      field.maxLength = 20;
      field.placeholder = 'e.g. CMPT 280';
      field.setAttribute('aria-label', `Course code for ${term.name}`);
      const add = document.createElement('button');
      add.type = 'submit';
      add.className = 'button secondary';
      add.textContent = 'Add course';
      form.append(field, add);
      form.addEventListener('submit', event => {
        event.preventDefault();
        const code = courseCode(field.value);
        if (!code) { message.textContent = 'Enter a course code like CMPT 280.'; return; }
        if (terms.some(value => value.courses.includes(code))) {
          message.textContent = `${code} is already in the semester draft.`;
          return;
        }
        if (terms.reduce((sum, value) => sum + value.courses.length, 0) >= 100) {
          message.textContent = 'This draft already contains 100 courses.';
          return;
        }
        term.courses.push(code);
        update();
        list.children[index]?.querySelector('input').focus();
      });
      box.append(form);
      list.append(box);
    }
  }

  el('term-form').addEventListener('submit', event => {
    event.preventDefault();
    const field = el('term-name');
    const name = field.value.trim();
    if (!name) return;
    if (terms.length >= 16) { message.textContent = 'This draft already contains 16 terms.'; return; }
    terms.push({name, courses: []});
    field.value = '';
    update();
    list.lastElementChild?.querySelector('input').focus();
  });

  check.addEventListener('click', async () => {
    if (!terms.some(term => term.courses.length)) {
      message.textContent = 'Add courses to the draft first.';
      return;
    }
    const controller = new AbortController();
    request = controller;
    check.disabled = true;
    message.textContent = 'Checking prerequisite order…';
    try {
      const result = await api('/api/planner/sequence', {terms: terms.map(term => term.courses), completed: getCompleted()}, {signal: controller.signal});
      if (controller.signal.aborted) return;
      checks = result.terms;
      render();
      message.textContent = 'Checked against completed courses and earlier draft terms. Open uncached courses in Course Explorer to check their rules.';
    } catch (error) {
      if (!controller.signal.aborted) message.textContent = error.message;
    } finally {
      if (request === controller) check.disabled = false;
    }
  });
  render();
  return invalidate;
}
