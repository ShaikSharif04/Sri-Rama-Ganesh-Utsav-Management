(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const modal = 'expenseModal';
  const defaultTemplate = `🙏 శ్రీ రామ గణేష్ ఉత్సవం, నాగిలిగొండ్ (గ్రామం), ఖమ్మం తరఫున మీకు నమస్కారం.\n\nఈ సంవత్సరం ఉత్సవాల ఖర్చుల వివరాలు:\n\n{{expense_table}}\n\nఆర్థిక వివరాలు:\nమొత్తం అందిన చందా: {{total_chanda}}\nమొత్తం ఖర్చులు: {{total_expenses}}\nమిగిలిన చందా: {{remaining_balance}}\n\nధన్యవాదాలు 🙏`;
  let queue = [];
  let queueIndex = 0;
  let lastRenderedMessage = '';
  const recipientBoxes = () => $$('.expense-recipient-check');
  const selectedIds = () => recipientBoxes().filter(box => box.checked).map(box => box.value);
  const selectedAudience = () => $('input[name="expenseAudience"]:checked')?.value || 'all';
  const updateCount = () => { $('#expenseRecipientCount').textContent = `${selectedIds().length} selected`; };
  const applyAudience = (audience) => {
    recipientBoxes().forEach(box => {
      if (audience === 'all') box.checked = true;
      else if (audience === 'pending') box.checked = box.dataset.status === 'pending';
      // 'manual' deliberately keeps the current check marks for manual adjustment.
    });
    updateCount();
  };
  const renderExpensePreview = async () => {
    const template = $('#expenseTemplate').value;
    $('#expensePreview').textContent = 'Updating expense summary…';
    try {
      const response = await fetch('/api/expense-message', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Unable to build expense summary.');
      lastRenderedMessage = data.message;
      $('#expensePreview').textContent = data.message || 'No expense records available.';
      const container = $('#expensePreviewTable');
      container.innerHTML = '';
      const table = document.createElement('table');
      table.innerHTML = '<thead><tr><th>S.No.</th><th>Particulars</th><th>Amount</th></tr></thead><tbody></tbody>';
      const body = $('tbody', table);
      if (data.rows?.length) {
        data.rows.forEach((row, index) => {
          const tr = document.createElement('tr');
          [String(index + 1), `${row.category} – ${row.description}`, row.amount].forEach(value => {
            const td = document.createElement('td'); td.textContent = value; tr.appendChild(td);
          });
          body.appendChild(tr);
        });
      } else {
        const tr = document.createElement('tr');
        const td = document.createElement('td'); td.colSpan = 3; td.textContent = 'No expense entries yet.';
        tr.appendChild(td); body.appendChild(tr);
      }
      const totals = [
        ['TOTAL EXPENSES', data.total],
      ];
      totals.forEach(([label, value]) => {
        const tr = document.createElement('tr');
        const name = document.createElement('td'); name.colSpan = 2; name.textContent = label;
        const amount = document.createElement('td'); amount.textContent = '₹' + Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
        tr.append(name, amount); body.appendChild(tr);
      });
      container.appendChild(table);
      const summary = document.createElement('table');
      summary.className = 'expense-financial-summary';
      summary.innerHTML = '<thead><tr><th colspan="2">CHANDA &amp; BALANCE SUMMARY</th></tr></thead><tbody></tbody>';
      const summaryBody = $('tbody', summary);
      [
        ['Total Chanda Received', data.total_chanda],
        ['Total Expenses', data.total],
        ['Remaining Chanda Balance', data.remaining_balance]
      ].forEach(([label, value]) => {
        const tr = document.createElement('tr');
        const name = document.createElement('td'); name.textContent = label;
        const amount = document.createElement('td'); amount.textContent = '₹' + Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
        tr.append(name, amount); summaryBody.appendChild(tr);
      });
      container.appendChild(summary);
    } catch (error) {
      $('#expensePreview').textContent = error.message;
    }
  };
  const openComposer = () => {
    window.openAppModal(modal);
    recipientBoxes().forEach(box => { box.checked = true; });
    const allRadio = $('input[name="expenseAudience"][value="all"]'); if (allRadio) allRadio.checked = true;
    $('#expenseQueueCard').hidden = true; queue = []; queueIndex = 0;
    updateCount(); renderExpensePreview();
  };
  $('#openExpenseComposer')?.addEventListener('click', openComposer);
  $('#expenseTemplate')?.addEventListener('input', renderExpensePreview);
  $$('input[name="expenseAudience"]').forEach(radio => radio.addEventListener('change', () => { applyAudience(radio.value); }));
  recipientBoxes().forEach(box => box.addEventListener('change', updateCount));
  $('#resetExpenseTemplate')?.addEventListener('click', () => { $('#expenseTemplate').value = defaultTemplate; renderExpensePreview(); });
  $$('.token[data-insert]').forEach(button => button.addEventListener('click', () => {
    const textarea = $('#expenseTemplate'); const token = button.dataset.insert;
    const start = textarea.selectionStart; const end = textarea.selectionEnd;
    textarea.setRangeText(token, start, end, 'end'); textarea.focus(); textarea.dispatchEvent(new Event('input'));
  }));

  const openNext = () => {
    if (!queue.length || queueIndex >= queue.length) {
      $('#expenseQueueStatus').textContent = 'All messages have been opened. Please confirm you pressed Send in WhatsApp for each person.';
      $('#openNextExpense').disabled = true; $('#openNextExpense').textContent = 'Queue completed'; return;
    }
    const item = queue[queueIndex];
    if (!item.phone) {
      queueIndex++; window.showToast(`No valid phone number for ${item.name}. Skipped.`); openNext(); return;
    }
    const whatsappWindow = window.open(item.url, '_blank');
    if (whatsappWindow) whatsappWindow.opener = null;
    queueIndex++;
    $('#expenseQueueStatus').textContent = `Opened ${queueIndex} of ${queue.length}: ${item.name}. Press Send in WhatsApp, then continue.`;
    $('#openNextExpense').disabled = queueIndex >= queue.length;
    $('#openNextExpense').textContent = queueIndex >= queue.length ? 'Queue completed' : `Open next (${queueIndex + 1}/${queue.length}) →`;
  };
  $('#openNextExpense')?.addEventListener('click', openNext);
  $('#startExpenseQueue')?.addEventListener('click', async () => {
    const ids = selectedIds();
    if (!ids.length) { window.showToast('Please select at least one recipient.'); return; }
    const button = $('#startExpenseQueue'); button.disabled = true; button.textContent = 'Preparing…';
    try {
      // Refresh the message at send-time so any expense entered moments ago is included.
      const expenseResponse = await fetch('/api/expense-message', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template: $('#expenseTemplate').value })
      });
      const expenseData = await expenseResponse.json();
      if (!expenseResponse.ok) throw new Error(expenseData.error || 'Could not build expense summary.');
      lastRenderedMessage = expenseData.message;
      const response = await fetch('/api/message-batch', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ person_ids: ids, template: lastRenderedMessage })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not prepare WhatsApp messages.');
      queue = result.items; queueIndex = 0;
      $('#expenseQueueCard').hidden = false;
      $('#expenseQueueStatus').textContent = `${queue.length} message(s) ready with the complete expense summary.`;
      $('#openNextExpense').disabled = false;
      $('#openNextExpense').textContent = 'Open first person in WhatsApp →';
    } catch (error) { window.showToast(error.message); }
    finally { button.disabled = false; button.textContent = '➤ Start WhatsApp Sending'; }
  });

  updateCount();
  renderExpensePreview();
  if (window.EXPENSES_COMPOSE_ON_LOAD) openComposer();
})();
