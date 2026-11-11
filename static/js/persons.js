(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const chandaModal = 'chandaModal';
  const individualModal = 'individualWhatsappModal';
  const defaultTemplate = `🙏 శ్రీ రామ గణేష్ ఉత్సవానికి చందా అందించినందుకు హృదయపూర్వక ధన్యవాదాలు.\n\n{{name}} గారు, మీరు అందించిన చందా మొత్తం: {{amount_received}}.\n\nధన్యవాదాలు 🙏`;
  let initialSelection = [];
  let queue = [];
  let queueIndex = 0;
  let individualPerson = null;

  const money = value => '₹' + Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  const normalizePhone = raw => {
    let digits = String(raw || '').replace(/\D/g, '');
    if (digits.length === 11 && digits.startsWith('0')) digits = digits.slice(1);
    if (digits.length === 10 && /^[6-9]/.test(digits)) return '91' + digits;
    if (digits.length === 12 && digits.startsWith('91')) return digits;
    return '';
  };
  const contactBoxes = () => $$('.modal-person-check');
  const getCheckedIds = () => contactBoxes().filter(box => box.checked).map(box => box.value);

  const renderChandaMessage = person => {
    let message = $('#chandaTemplate')?.value || '';
    const name = person?.name || '[Person Name]';
    const amount = person ? money(person.amount) : '₹[Amount]';
    return message.replaceAll('{{name}}', name).replaceAll('{{amount_received}}', amount);
  };
  const updatePreview = () => {
    const selected = contactBoxes().find(box => box.checked) || contactBoxes()[0];
    const ids = getCheckedIds();
    const selectedPerson = selected ? {
      name: selected.closest('label')?.querySelector('span')?.textContent?.trim() || 'Contributor',
      amount: selected.dataset.received || 0
    } : null;
    $('#chandaPreview').textContent = renderChandaMessage(selectedPerson);
    $('#chandaRecipientCount').textContent = `${ids.length} selected`;
  };
  const setAudience = audience => {
    contactBoxes().forEach(box => {
      if (audience === 'all') box.checked = true;
      else if (audience === 'pending') box.checked = box.dataset.status === 'pending';
      else box.checked = initialSelection.includes(box.value);
    });
    updatePreview();
  };
  const setRecipientSelection = ids => {
    initialSelection = ids.map(String);
    contactBoxes().forEach(box => { box.checked = initialSelection.includes(box.value); });
    const radio = $('input[name="chandaAudience"][value="selected"]');
    if (radio) radio.checked = true;
    $('#chandaQueueCard').hidden = true;
    queue = []; queueIndex = 0;
    updatePreview();
  };
  const openComposer = ids => {
    setRecipientSelection(ids || []);
    window.openAppModal(chandaModal);
  };

  // Save buttons are normal form submissions. The WhatsApp button only prepares a message.
  const personForm = $('#personForm');
  $('#openIndividualWhatsapp')?.addEventListener('click', () => {
    if (!personForm.reportValidity()) return;
    const formData = new FormData(personForm);
    const phone = normalizePhone(formData.get('phone'));
    if (!phone) { window.showToast('Enter a valid Indian mobile number.'); return; }
    individualPerson = {
      name: String(formData.get('name') || '').trim(),
      phone,
      amount: Number(formData.get('amount_received') || 0)
    };
    $('#individualWhatsappTemplate').value = defaultTemplate;
    window.openAppModal(individualModal);
  });
  $('#confirmIndividualWhatsapp')?.addEventListener('click', () => {
    if (!individualPerson) return;
    const message = $('#individualWhatsappTemplate').value
      .replaceAll('{{name}}', individualPerson.name)
      .replaceAll('{{amount_received}}', money(individualPerson.amount));
    const url = `https://wa.me/${individualPerson.phone}?text=${encodeURIComponent(message)}`;
    const whatsappWindow = window.open(url, '_blank');
    if (whatsappWindow) whatsappWindow.opener = null;
    window.closeAppModal(individualModal);
    window.showToast('WhatsApp opened. Press Send to deliver the message.');
  });

  // Table select-all and bulk send.
  const selectAll = $('#selectAllPersons');
  const tableChecks = $$('.person-check');
  const updateTableCount = () => {
    const count = tableChecks.filter(box => box.checked).length;
    $('#selectedCount').textContent = `${count} selected`;
    $('#sendSelectedChanda').disabled = count === 0;
    if (selectAll) selectAll.checked = tableChecks.length > 0 && count === tableChecks.length;
  };
  tableChecks.forEach(box => box.addEventListener('change', updateTableCount));
  selectAll?.addEventListener('change', () => {
    tableChecks.forEach(box => { box.checked = selectAll.checked; });
    updateTableCount();
  });
  $('#sendSelectedChanda')?.addEventListener('click', () => openComposer(tableChecks.filter(box => box.checked).map(box => box.value)));

  // Send a single WhatsApp message for an existing person.
  $$('.whatsapp-one').forEach(button => button.addEventListener('click', () => {
    const checkbox = tableChecks.find(box => box.value === button.dataset.id);
    if (!checkbox) return;
    individualPerson = {
      name: checkbox.dataset.personName || 'Contributor',
      phone: normalizePhone(checkbox.dataset.phone),
      amount: Number(checkbox.dataset.received || 0)
    };
    if (!individualPerson.phone) { window.showToast('This person has an invalid phone number.'); return; }
    $('#individualWhatsappTemplate').value = defaultTemplate;
    window.openAppModal(individualModal);
  }));

  // Edit an existing person and its Paid/Pending status.
  $$('.edit-person').forEach(button => button.addEventListener('click', () => {
    const form = $('#editPersonForm');
    form.action = `/persons/${button.dataset.id}/update`;
    $('#editName').value = button.dataset.name;
    $('#editPhone').value = button.dataset.phone;
    $('#editReceived').value = button.dataset.received;
    $('#editStatus').value = button.dataset.status || 'pending';
    window.openAppModal('editPersonModal');
  }));

  // Bulk message editor and recipient filters.
  $('#chandaTemplate')?.addEventListener('input', updatePreview);
  $$('input[name="chandaAudience"]').forEach(radio => radio.addEventListener('change', () => setAudience(radio.value)));
  contactBoxes().forEach(box => box.addEventListener('change', updatePreview));
  $('#resetChandaTemplate')?.addEventListener('click', () => {
    $('#chandaTemplate').value = defaultTemplate;
    updatePreview();
  });
  $$('.token[data-insert]').forEach(button => button.addEventListener('click', () => {
    const textarea = $('#chandaTemplate');
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    textarea.setRangeText(button.dataset.insert, start, end, 'end');
    textarea.focus();
    textarea.dispatchEvent(new Event('input'));
  }));

  const openNext = () => {
    if (!queue.length || queueIndex >= queue.length) {
      $('#chandaQueueStatus').textContent = 'All messages have been opened. Please make sure you pressed Send in WhatsApp for each person.';
      $('#openNextChanda').disabled = true;
      $('#openNextChanda').textContent = 'Queue completed';
      return;
    }
    const item = queue[queueIndex];
    if (!item.phone) {
      queueIndex++;
      window.showToast(`No valid phone number for ${item.name}. Skipped.`);
      openNext();
      return;
    }
    const whatsappWindow = window.open(item.url, '_blank');
    if (whatsappWindow) whatsappWindow.opener = null;
    queueIndex++;
    $('#chandaQueueStatus').textContent = `Opened ${queueIndex} of ${queue.length}: ${item.name}. Press Send in WhatsApp, then continue.`;
    $('#openNextChanda').disabled = queueIndex >= queue.length;
    $('#openNextChanda').textContent = queueIndex >= queue.length ? 'Queue completed' : `Open next (${queueIndex + 1}/${queue.length}) →`;
  };
  $('#openNextChanda')?.addEventListener('click', openNext);
  $('#startChandaQueue')?.addEventListener('click', async () => {
    const ids = getCheckedIds();
    if (!ids.length) { window.showToast('Please select at least one recipient.'); return; }
    const button = $('#startChandaQueue');
    button.disabled = true;
    button.textContent = 'Preparing…';
    try {
      const response = await fetch('/api/message-batch', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ person_ids: ids, template: $('#chandaTemplate').value })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not prepare messages.');
      queue = result.items;
      queueIndex = 0;
      $('#chandaQueueCard').hidden = false;
      $('#chandaQueueStatus').textContent = `${queue.length} personalized message(s) ready. Open them one at a time.`;
      $('#openNextChanda').disabled = false;
      $('#openNextChanda').textContent = 'Open first person in WhatsApp →';
    } catch (error) {
      window.showToast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = '➤ Start WhatsApp Sending';
    }
  });

  updateTableCount();
  updatePreview();
})();
