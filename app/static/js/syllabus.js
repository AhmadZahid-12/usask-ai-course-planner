const upload = document.querySelector('#syllabus-upload');
const uploadButton = upload.querySelector('button[type="submit"]');
const file = document.querySelector('#syllabus-file');
const review = document.querySelector('#syllabus-review');
const form = document.querySelector('#syllabus-approval');
const proposals = document.querySelector('#syllabus-candidates');
const template = document.querySelector('#syllabus-card');
const approvalButton = document.querySelector('#syllabus-approve');
const uploadStatus = document.querySelector('#syllabus-upload-message');
const approvalStatus = document.querySelector('#syllabus-approval-message');
const calendarResult = document.querySelector('#syllabus-calendar-result');

const precisionLabels = {
  timed: ['Date and time found', 'eligible'],
  date: ['Date found', 'complete'],
  ambiguous: ['Needs verification', 'review'],
};

function report(target, text, error = false) {
  target.hidden = !text;
  target.textContent = text;
  target.classList.toggle('feedback-error', error);
}

function selectedCards() {
  return [...proposals.children].filter(card => !card.disabled && card.querySelector('[name="approved"]').checked);
}

function syncSelection() {
  const selected = selectedCards().length;
  approvalButton.disabled = !selected || uploadButton.disabled;
  approvalButton.textContent = selected ? `Add ${selected} ${selected === 1 ? 'deadline' : 'deadlines'}` : 'Add selected deadlines';
}

function proposalCard(candidate) {
  const card = template.content.firstElementChild.cloneNode(true);
  card.dataset.token = candidate.token;
  card.querySelector('legend').textContent = candidate.title;
  const [label, tone] = precisionLabels[candidate.precision];
  const badge = card.querySelector('.syllabus-precision');
  badge.classList.add(tone);
  badge.textContent = label;
  card.querySelector('.syllabus-position').textContent = candidate.page == null ? 'Text upload' : `PDF page ${candidate.page}`;
  card.querySelector('.syllabus-reason').textContent = candidate.reason;
  card.querySelector('blockquote').textContent = candidate.evidence;
  const approval = card.querySelector('[name="approved"]');
  approval.setAttribute('aria-label', `Approve ${candidate.title}`);
  for (const name of ['title', 'category', 'date', 'time', 'course_code']) {
    card.querySelector(`[name="${name}"]`).value = candidate[name];
  }
  card.querySelector('.syllabus-reject').addEventListener('click', () => {
    const adjacent = card.nextElementSibling || card.previousElementSibling;
    card.remove();
    if (adjacent) adjacent.querySelector('[name="approved"]').focus();
    else approvalStatus.focus();
    report(approvalStatus, proposals.children.length ? `Rejected ${candidate.title}.` : 'No deadlines remain to review.');
    syncSelection();
  });
  return card;
}

async function post(url, options) {
  const response = await fetch(url, options);
  const result = await response.json().catch(() => null);
  if (!response.ok || !result) throw new Error(result?.error || 'The request could not be completed. Try again.');
  return result;
}

file.addEventListener('change', () => {
  document.querySelector('#syllabus-file-note').textContent = file.files[0]?.name || 'No file selected';
});

upload.addEventListener('submit', async event => {
  event.preventDefault();
  if (uploadButton.disabled) return;
  const body = new FormData(upload);
  uploadButton.disabled = true;
  syncSelection();
  upload.setAttribute('aria-busy', 'true');
  report(uploadStatus, 'Reading the syllabus…');
  try {
    const result = await post(upload.action, {method: 'POST', body});
    calendarResult.hidden = true;
    proposals.replaceChildren(...result.candidates.map(proposalCard));
    if (!result.candidates.length) {
      review.hidden = true;
      report(uploadStatus, 'No reviewable deadlines found. Try uploading the schedule pages or a text version.');
      return;
    }
    document.querySelector('#syllabus-summary').textContent = result.limit_reached
      ? 'Showing up to 75 suggestions. Upload individual schedule pages to find additional dates.'
      : `${result.candidates.length} ${result.candidates.length === 1 ? 'suggestion' : 'suggestions'} to verify.`;
    report(uploadStatus, '');
    report(approvalStatus, 'Select the deadlines you want to import.');
    review.hidden = false;
    syncSelection();
    const heading = document.querySelector('#syllabus-review-title');
    requestAnimationFrame(() => {
      heading.focus({preventScroll: true});
      heading.scrollIntoView({block: 'start'});
    });
  } catch (error) {
    report(uploadStatus, error.message || 'Unable to read this syllabus.', true);
  } finally {
    uploadButton.disabled = false;
    syncSelection();
    upload.removeAttribute('aria-busy');
  }
});

form.addEventListener('change', syncSelection);
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (approvalButton.disabled) return;
  const selected = selectedCards();
  const zone = document.querySelector('#syllabus-zone');
  const events = [];
  for (const card of selected) {
    const fields = Object.fromEntries([...card.querySelectorAll('input, select')].map(input => [input.name, input.value]));
    if (!fields.title.trim() || !fields.date) {
      report(approvalStatus, 'Enter a title and date for every selected deadline.', true);
      card.querySelector(fields.title.trim() ? '[name="date"]' : '[name="title"]').focus();
      return;
    }
    if (fields.time && !zone.value.trim()) {
      report(approvalStatus, 'Enter a time zone for timed deadlines.', true);
      zone.focus();
      return;
    }
    const {approved, ...details} = fields;
    events.push({...details, timezone: zone.value.trim(), token: card.dataset.token});
  }

  const cards = [...proposals.querySelectorAll('fieldset:not(:disabled)')];
  cards.forEach(card => { card.disabled = true; });
  uploadButton.disabled = true;
  approvalButton.disabled = true;
  report(approvalStatus, 'Adding reviewed deadlines…');
  let saved = false;
  try {
    const result = await post(review.dataset.approveUrl, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({events}),
    });
    selected.forEach(card => {
      const badge = card.querySelector('.syllabus-precision');
      badge.className = 'badge complete';
      badge.textContent = 'Processed';
      card.querySelector('.syllabus-reject').hidden = true;
    });
    saved = true;
    const added = result.events.length;
    const duplicates = result.duplicate_count;
    calendarResult.hidden = !added;
    if (added) {
      const url = new URL(calendarResult.href);
      url.searchParams.set('event', String(result.events[0].id));
      calendarResult.href = url.href;
      calendarResult.textContent = added === 1 ? 'View imported deadline' : 'View first imported deadline';
    }
    report(approvalStatus, `${added} added to the calendar.${duplicates ? ` ${duplicates} already in the calendar.` : ''}`);
    approvalStatus.focus();
  } catch (error) {
    report(approvalStatus, error.message || 'Unable to add the reviewed deadlines.', true);
    approvalStatus.focus();
  } finally {
    cards.forEach(card => { card.disabled = saved && selected.includes(card); });
    uploadButton.disabled = false;
    syncSelection();
  }
});
