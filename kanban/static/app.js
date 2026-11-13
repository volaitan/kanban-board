const WIP_LIMIT = Number(document.body.dataset.wipLimit);
const dialog = document.getElementById('card-dialog');
const form = document.getElementById('card-form');
const formError = document.getElementById('form-error');
const deleteBtn = document.getElementById('delete-btn');
let cards = [];
let editingId = null;

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function toast(message) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove('show'), 2800);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function cardHtml(c) {
  const today = new Date().toISOString().slice(0, 10);
  const overdue = c.due_date && c.due_date < today && c.status !== 'done';
  const tags = [
    `<span class="tag">${c.priority}</span>`,
    c.points != null ? `<span class="tag">${c.points} pts</span>` : '',
    c.assignee ? `<span class="tag">👤 ${escapeHtml(c.assignee)}</span>` : '',
    c.due_date ? `<span class="tag ${overdue ? 'overdue' : ''}">📅 ${c.due_date}</span>` : '',
  ].join('');
  return `<article class="card" draggable="true" data-id="${c.id}" data-priority="${c.priority}" tabindex="0">
    <h3>${escapeHtml(c.title)}</h3>
    ${c.description ? `<p>${escapeHtml(c.description)}</p>` : ''}
    <div class="meta">${tags}</div>
  </article>`;
}

function render() {
  document.querySelectorAll('.cards').forEach(list => {
    const status = list.dataset.status;
    const inCol = cards.filter(c => c.status === status).sort((a, b) => a.position - b.position);
    list.innerHTML = inCol.map(cardHtml).join('');
    const count = document.querySelector(`[data-count-for="${status}"]`);
    count.textContent = status === 'in_progress' ? `${inCol.length}/${WIP_LIMIT}` : inCol.length;
    count.classList.toggle('full', status === 'in_progress' && inCol.length >= WIP_LIMIT);
  });
}

async function refresh() {
  cards = await api('/api/cards');
  render();
  const s = await api('/api/stats');
  document.getElementById('progress-fill').style.width = `${s.percent_complete}%`;
  document.getElementById('progress-text').textContent =
    `${s.percent_complete}% complete (${s.done_points}/${s.total_points} pts)`;
}

// ---------- Dialog (create / edit) ----------
function openDialog(card = null) {
  editingId = card ? card.id : null;
  form.reset();
  formError.textContent = '';
  document.getElementById('dialog-title').textContent = card ? 'Edit card' : 'New card';
  deleteBtn.hidden = !card;
  if (card) {
    for (const key of ['title', 'description', 'priority', 'assignee', 'points', 'due_date']) {
      form.elements[key].value = card[key] ?? '';
    }
  }
  dialog.showModal();
  form.elements.title.focus();
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(form));
  try {
    if (editingId) await api(`/api/cards/${editingId}`, { method: 'PATCH', body });
    else await api('/api/cards', { method: 'POST', body });
    dialog.close();
    await refresh();
  } catch (err) {
    formError.textContent = err.message;
  }
});

deleteBtn.addEventListener('click', async () => {
  if (!editingId) return;
  await api(`/api/cards/${editingId}`, { method: 'DELETE' });
  dialog.close();
  toast('Card deleted');
  await refresh();
});

document.getElementById('cancel-btn').addEventListener('click', () => dialog.close());
document.getElementById('new-card-btn').addEventListener('click', () => openDialog());

document.getElementById('board').addEventListener('click', (e) => {
  const el = e.target.closest('.card');
  if (el) openDialog(cards.find(c => c.id === Number(el.dataset.id)));
});
document.getElementById('board').addEventListener('keydown', (e) => {
  const el = e.target.closest('.card');
  if (el && e.key === 'Enter') openDialog(cards.find(c => c.id === Number(el.dataset.id)));
});

// ---------- Drag and drop ----------
let draggedId = null;

document.addEventListener('dragstart', (e) => {
  const el = e.target.closest('.card');
  if (!el) return;
  draggedId = Number(el.dataset.id);
  el.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
});

document.addEventListener('dragend', (e) => {
  e.target.closest('.card')?.classList.remove('dragging');
  document.querySelectorAll('.drag-over').forEach(l => l.classList.remove('drag-over'));
});

function dropIndex(list, y) {
  const others = [...list.querySelectorAll('.card:not(.dragging)')];
  const idx = others.findIndex(c => {
    const box = c.getBoundingClientRect();
    return y < box.top + box.height / 2;
  });
  return idx === -1 ? others.length : idx;
}

document.querySelectorAll('.cards').forEach(list => {
  list.addEventListener('dragover', (e) => {
    e.preventDefault();
    list.classList.add('drag-over');
  });
  list.addEventListener('dragleave', () => list.classList.remove('drag-over'));
  list.addEventListener('drop', async (e) => {
    e.preventDefault();
    list.classList.remove('drag-over');
    if (draggedId == null) return;
    try {
      await api(`/api/cards/${draggedId}/move`, {
        method: 'POST',
        body: { status: list.dataset.status, position: dropIndex(list, e.clientY) },
      });
    } catch (err) {
      toast(err.message);
    }
    draggedId = null;
    await refresh();
  });
});

refresh();
