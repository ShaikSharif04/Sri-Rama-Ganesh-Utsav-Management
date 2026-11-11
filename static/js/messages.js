(() => {
  const $ = (id) => document.getElementById(id);
  const defaultChanda = `🙏 శ్రీ రామ గణేష్ ఉత్సవానికి చందా అందించినందుకు హృదయపూర్వక ధన్యవాదాలు.\n\n{{name}} గారు, మీరు అందించిన చందా మొత్తం {{amount_received}}.\n\nధన్యవాదాలు 🙏\n\n{{location}}`;
  const defaultExpense = `🙏 శ్రీ రామ గణేష్ ఉత్సవ సంఘం – {{location}}\n\nప్రియమైన సభ్యులారా,\nఈ సంవత్సరం గణేష్ ఉత్సవ ఖర్చుల వివరాలు:\n\n{{expense_table}}\n\n{{financial_summary}}\n\nమీ సహకారానికి ధన్యవాదాలు 🙏`;
  let chandaQueue = [], expenseQueue = [], chandaIndex = 0, expenseIndex = 0;
  let expenseData = null;

  const ids = (group) => [...document.querySelectorAll(`.bulk-person[data-group="${group}"]:checked`)].map(x => Number(x.value));
  const checks = (group) => [...document.querySelectorAll(`.bulk-person[data-group="${group}"]`)];
  const setCount = (group) => {
    const count = ids(group).length;
    const target = $(group === 'chanda' ? 'chandaSelectedCount' : 'expenseSelectedCount');
    if (target) target.textContent = `${count} selected`;
    const all = $(group === 'chanda' ? 'chandaSelectAll' : 'expenseSelectAll');
    if (all) all.checked = checks(group).length > 0 && checks(group).every(x => x.checked);
  };
  const chooseAudience = (group, audience) => {
    checks(group).forEach(box => {
      const match = audience === 'all' || (audience === 'paid' && box.dataset.status === 'paid') || (audience === 'pending' && box.dataset.status === 'pending');
      box.checked = match;
    });
    setCount(group);
    if (group === 'expenses') refreshExpensePreview();
    else refreshChandaPreview();
  };
  const selectedPeople = (group) => checks(group).filter(x => x.checked);
  const replaceChanda = (template, person) => template
    .replaceAll('{{name}}', person?.dataset.name || 'Member Name')
    .replaceAll('{{amount_received}}', `₹${Number(person?.dataset.amount || 0).toLocaleString('en-IN')}`)
    .replaceAll('{{location}}', 'Nagiligond (Vill), Khammam');
  const refreshChandaPreview = () => {
    const first = selectedPeople('chanda')[0];
    $('chandaMessagePreview').textContent = replaceChanda($('chandaMessage').value, first);
  };
  const getExpensePreview = async () => {
    const selected = ids('expenses');
    if (!selected.length) return null;
    const response = await fetch('/api/expense-message', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({person_ids: selected, template: $('expenseMessage').value})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Unable to prepare expense summary.');
    return data;
  };
  const refreshExpensePreview = async () => {
    if (!ids('expenses').length) {
      $('expenseMessagePreview').textContent = 'Select at least one member to preview the expense summary.';
      return;
    }
    try {
      expenseData = await getExpensePreview();
      $('expenseMessagePreview').textContent = expenseData.message;
      $('financialPreview').innerHTML = `
        <div><span>Total Paid Chanda</span><strong>₹${expenseData.total_chanda.toLocaleString('en-IN')}</strong></div>
        <div><span>Total Expenses</span><strong>₹${expenseData.total.toLocaleString('en-IN')}</strong></div>
        <div><span>Remaining Balance</span><strong>₹${expenseData.remaining_balance.toLocaleString('en-IN')}</strong></div>`;
    } catch (error) { $('expenseMessagePreview').textContent = error.message; }
  };
  const switchTab = (tab) => {
    document.querySelectorAll('[data-message-tab]').forEach(button => button.classList.toggle('active', button.dataset.messageTab === tab));
    $('chandaWorkspace').hidden = tab !== 'chanda';
    $('expensesWorkspace').hidden = tab !== 'expenses';
    if (tab === 'expenses') refreshExpensePreview();
  };
  const openNext = (queue, index, button, progress, title) => {
    if (!queue.length) return;
    if (index >= queue.length) {
      button.disabled = true;
      button.textContent = '✓ Queue completed';
      progress.textContent = `Completed opening all ${queue.length} selected chats. Make sure each message was sent in WhatsApp.`;
      return;
    }
    const item = queue[index];
    const win = window.open(item.url, '_blank');
    if (win) win.opener = null;
    if (!win) {
      progress.textContent = 'Your browser blocked the new tab. Allow pop-ups for this site, then click again.';
      return;
    }
    const next = index + 1;
    progress.textContent = `Opened ${next} of ${queue.length}: ${item.name} (${item.phone}). Send the message in WhatsApp, then return and continue.`;
    button.textContent = next < queue.length ? `Open next: ${queue[next].name} →` : 'Finish queue';
    button.dataset.index = String(next);
    title.textContent = `WhatsApp queue · ${next}/${queue.length}`;
    if (next >= queue.length) button.textContent = 'Finish queue';
  };

  document.querySelectorAll('[data-message-tab]').forEach(button => button.addEventListener('click', () => switchTab(button.dataset.messageTab)));
  ['chanda', 'expenses'].forEach(group => {
    checks(group).forEach(box => box.addEventListener('change', () => {
      setCount(group);
      if (group === 'chanda') refreshChandaPreview(); else refreshExpensePreview();
    }));
    $(group === 'chanda' ? 'chandaSelectAll' : 'expenseSelectAll')?.addEventListener('change', event => {
      checks(group).forEach(box => box.checked = event.target.checked);
      setCount(group);
      if (group === 'chanda') refreshChandaPreview(); else refreshExpensePreview();
    });
    $(group === 'chanda' ? 'chandaAudience' : 'expenseAudience')?.addEventListener('change', event => chooseAudience(group, event.target.value));
  });
  $('chandaMessage')?.addEventListener('input', refreshChandaPreview);
  $('expenseMessage')?.addEventListener('input', refreshExpensePreview);
  $('resetChandaMessage')?.addEventListener('click', () => { $('chandaMessage').value = defaultChanda; refreshChandaPreview(); });
  $('resetExpenseMessage')?.addEventListener('click', () => { $('expenseMessage').value = defaultExpense; refreshExpensePreview(); });

  $('startChandaBulk')?.addEventListener('click', async () => {
    const personIds = ids('chanda');
    if (!personIds.length) return window.showToast?.('Select at least one contributor first.');
    const response = await fetch('/api/message-batch', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({person_ids:personIds, template:$('chandaMessage').value})});
    const data = await response.json();
    if (!response.ok) return window.showToast?.(data.error || 'Could not prepare messages.');
    chandaQueue = data.items; chandaIndex = 0;
    $('chandaQueue').hidden = false;
    $('chandaQueueTitle').textContent = `WhatsApp queue · ${chandaQueue.length} recipients`;
    $('chandaQueueProgress').textContent = `Ready to open ${chandaQueue.length} personalized chats. Each message must be sent manually in WhatsApp.`;
    $('chandaOpenNext').disabled = false; $('chandaOpenNext').dataset.index = '0'; $('chandaOpenNext').textContent = `Open first: ${chandaQueue[0].name} →`;
    $('chandaOpenNext').onclick = () => { const i = Number($('chandaOpenNext').dataset.index || 0); openNext(chandaQueue, i, $('chandaOpenNext'), $('chandaQueueProgress'), $('chandaQueueTitle')); };
  });

  $('startExpenseBulk')?.addEventListener('click', async () => {
    if (!ids('expenses').length) return window.showToast?.('Select at least one member first.');
    try {
      const data = await getExpensePreview();
      expenseQueue = data.items || []; expenseIndex = 0;
      if (!expenseQueue.length) return window.showToast?.('No valid WhatsApp recipients were found.');
      $('expenseQueue').hidden = false;
      $('expenseQueueTitle').textContent = `WhatsApp queue · ${expenseQueue.length} recipients`;
      $('expenseQueueProgress').textContent = `Financial summary is ready for ${expenseQueue.length} selected members. Send each chat in WhatsApp.`;
      $('expenseOpenNext').disabled = false; $('expenseOpenNext').dataset.index = '0'; $('expenseOpenNext').textContent = `Open first: ${expenseQueue[0].name} →`;
      $('expenseOpenNext').onclick = () => { const i = Number($('expenseOpenNext').dataset.index || 0); openNext(expenseQueue, i, $('expenseOpenNext'), $('expenseQueueProgress'), $('expenseQueueTitle')); };
    } catch (error) { window.showToast?.(error.message); }
  });

  chooseAudience('chanda', 'paid');
  chooseAudience('expenses', 'paid');
})();
