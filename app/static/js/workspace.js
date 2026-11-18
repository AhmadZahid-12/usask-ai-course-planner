const removal = document.querySelector('#remove-material-dialog');
let pendingForm;

document.addEventListener('submit', event => {
  const form = event.target.closest('[data-remove-material]');
  if (!form || form.elements.confirmed.value === 'yes') return;
  event.preventDefault();
  pendingForm = form;
  removal.returnValue = 'cancel';
  removal.showModal();
});

removal.addEventListener('close', () => {
  if (removal.returnValue === 'remove' && pendingForm) {
    pendingForm.elements.confirmed.value = 'yes';
    pendingForm.requestSubmit();
  }
  pendingForm = undefined;
});
