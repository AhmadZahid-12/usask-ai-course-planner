const form = document.querySelector('#assistant-form');
let submitting = false;

form.addEventListener('submit', event => {
  if (submitting) {
    event.preventDefault();
    return;
  }
  submitting = true;
  form.setAttribute('aria-busy', 'true');
  document.querySelector('#assistant-message').textContent = event.submitter?.value === 'generate'
    ? 'Reading the official entry and generating a summary…'
    : 'Looking up the official course entry…';
});

window.addEventListener('pageshow', event => {
  if (event.persisted) {
    submitting = false;
    form.removeAttribute('aria-busy');
    document.querySelector('#assistant-message').textContent = 'Enter a course code to begin.';
  }
});
