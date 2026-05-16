// Lightweight UI enhancements: kanban DnD, flash auto-dismiss, button ripple.
// Only transform/opacity animations — runs on the GPU compositor, no layout thrash.

(function () {
  // -------- Auto-dismiss flash messages --------
  document.querySelectorAll('#flash .toast').forEach((el) => {
    setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(20px)'; }, 3500);
    setTimeout(() => el.remove(), 4000);
  });

  // -------- Button ripple effect (pure CSS-driven) --------
  document.addEventListener('pointerdown', (e) => {
    const btn = e.target.closest('.btn');
    if (!btn || btn.disabled) return;
    const rect = btn.getBoundingClientRect();
    const ripple = document.createElement('span');
    ripple.className = 'btn-ripple';
    const size = Math.max(rect.width, rect.height);
    ripple.style.width = ripple.style.height = size + 'px';
    ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
    ripple.style.top  = (e.clientY - rect.top  - size / 2) + 'px';
    btn.appendChild(ripple);
    setTimeout(() => ripple.remove(), 550);
  });

  // -------- Kanban drag-and-drop --------
  document.querySelectorAll('.kanban .kcard').forEach((card) => {
    card.setAttribute('draggable', 'true');
    card.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('text/id', card.dataset.id);
      e.dataTransfer.effectAllowed = 'move';
      card.style.opacity = '0.4';
      card.style.transform = 'scale(0.97)';
    });
    card.addEventListener('dragend', () => {
      card.style.opacity = '';
      card.style.transform = '';
    });
  });

  document.querySelectorAll('.kanban .column').forEach((col) => {
    col.addEventListener('dragover', (e) => { e.preventDefault(); col.classList.add('drag-over'); });
    col.addEventListener('dragleave', () => col.classList.remove('drag-over'));
    col.addEventListener('drop', async (e) => {
      e.preventDefault();
      col.classList.remove('drag-over');
      const id = e.dataTransfer.getData('text/id');
      const stage = col.dataset.stage;
      if (!id || !stage) return;
      try {
        const form = new FormData();
        form.append('stage', stage);
        const res = await fetch(`/candidates/${id}/move`, { method: 'POST', body: form });
        if (res.ok) location.reload();
      } catch (_) { location.reload(); }
    });
  });

  // -------- Smooth submit feedback (loading spinner on submit buttons) --------
  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', () => {
      const btn = form.querySelector('button[type=submit], button:not([type])');
      if (!btn) return;
      btn.classList.add('is-loading');
      btn.disabled = true;
      // Re-enable after 8s in case the page never navigates (defensive).
      setTimeout(() => { btn.classList.remove('is-loading'); btn.disabled = false; }, 8000);
    });
  });
})();
