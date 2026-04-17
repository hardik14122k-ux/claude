// Small enhancement JS — Kanban drag-and-drop + flash auto-dismiss.

(function () {
  // Auto-dismiss flash messages
  document.querySelectorAll('#flash .toast').forEach((el) => {
    setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(10px)'; }, 3000);
    setTimeout(() => el.remove(), 3500);
  });

  // Kanban drag-and-drop
  document.querySelectorAll('.kanban .kcard').forEach((card) => {
    card.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('text/id', card.dataset.id);
      e.dataTransfer.effectAllowed = 'move';
      card.style.opacity = '0.4';
    });
    card.addEventListener('dragend', () => { card.style.opacity = ''; });
  });

  document.querySelectorAll('.kanban .column').forEach((col) => {
    col.addEventListener('dragover', (e) => {
      e.preventDefault();
      col.classList.add('drag-over');
    });
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
      } catch (_) {
        location.reload();
      }
    });
  });
})();
