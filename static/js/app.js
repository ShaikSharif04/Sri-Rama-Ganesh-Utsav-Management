(() => {
  const toast = (message) => {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(window.__toastTimer);
    window.__toastTimer = setTimeout(() => el.classList.remove('show'), 3000);
  };
  const openModal = (id) => {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  };
  const closeModal = (id) => {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    if (!document.querySelector('.modal-backdrop.open')) document.body.style.overflow = '';
  };
  window.showToast = toast;
  window.openAppModal = openModal;
  window.closeAppModal = closeModal;
  document.addEventListener('click', (event) => {
    const close = event.target.closest('[data-close]');
    if (close) closeModal(close.dataset.close);
    if (event.target.classList.contains('modal-backdrop')) closeModal(event.target.id);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') document.querySelectorAll('.modal-backdrop.open').forEach(m => closeModal(m.id));
  });
  const menu = document.getElementById('mobileMenu');
  const sidebar = document.getElementById('sidebar');
  menu?.addEventListener('click', () => sidebar?.classList.toggle('open'));
  document.addEventListener('click', (event) => {
    if (window.innerWidth <= 760 && sidebar?.classList.contains('open') && !sidebar.contains(event.target) && !menu?.contains(event.target)) sidebar.classList.remove('open');
  });
})();
