const list = document.getElementById('submissionList');
const template = document.getElementById('submissionTemplate');
const searchInput = document.getElementById('searchInput');
let currentStatus = 'pending';
let allRows = [];

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value ?? '';
  return div.innerHTML;
}

function prettyType(value) {
  const map = { social: 'Fam social', clubwide: 'Clubwide IEEE event', quest: 'Quest', competition: 'Competition', other: 'Other' };
  return map[value] || value;
}

function ruleText(ok, yesText, noText) {
  return `${ok ? '✓' : '×'} ${ok ? yesText : noText}`;
}

function suggestedPoints(row) {
  if (row.event_type === 'clubwide') return row.member_count >= 4 && row.fam_head_present ? 1 : 0;
  if (row.event_type === 'social') return row.member_count >= 4 && row.fam_head_present && row.advertised_beforehand ? row.member_count : 0;
  return row.points_awarded || 0;
}

async function loadRows() {
  list.innerHTML = '<div class="loading-state">Loading submissions…</div>';
  const res = await fetch('/api/admin/submissions?status=all');
  if (res.status === 401) { location.href = '/admin/login'; return; }
  const data = await res.json();
  allRows = data.submissions || [];
  document.getElementById('pendingCount').textContent = allRows.filter(r => r.status === 'pending').length;
  document.getElementById('approvedCount').textContent = allRows.filter(r => r.status === 'approved').length;
  document.getElementById('deniedCount').textContent = allRows.filter(r => r.status === 'denied').length;
  renderRows();
}

function renderRows() {
  const q = searchInput.value.trim().toLowerCase();
  const rows = allRows.filter(r => (currentStatus === 'all' || r.status === currentStatus) &&
    (!q || `${r.family_name} ${r.event_title} ${r.submitter_name} ${r.description}`.toLowerCase().includes(q)));

  list.innerHTML = '';
  if (!rows.length) {
    list.innerHTML = '<div class="empty-admin"><strong>No submissions here.</strong><span>Try a different filter or search.</span></div>';
    return;
  }

  rows.forEach(row => {
    const node = template.content.cloneNode(true);
    const card = node.querySelector('.submission-card');
    node.querySelector('.proof-photo').src = row.photo_data;
    node.querySelector('.family-badge').textContent = row.family_name;
    node.querySelector('.event-title').textContent = row.event_title;
    node.querySelector('.event-description').textContent = row.description;
    node.querySelector('.event-date').textContent = new Date(`${row.event_date}T12:00:00`).toLocaleDateString(undefined, {month:'short', day:'numeric', year:'numeric'});
    node.querySelector('.submitter').textContent = row.submitter_name;
    node.querySelector('.member-count').textContent = `${row.member_count} people`;
    node.querySelector('.event-type').textContent = prettyType(row.event_type);

    const status = node.querySelector('.review-status');
    status.textContent = row.status;
    status.classList.add(row.status);

    const membersOk = Number(row.member_count) >= 4;
    const headOk = Boolean(row.fam_head_present);
    const advertisedOk = Boolean(row.advertised_beforehand);
    const membersRule = node.querySelector('.rule-members');
    membersRule.textContent = ruleText(membersOk, `${row.member_count} members (minimum met)`, `${row.member_count} members (needs 4+)`);
    membersRule.classList.add(membersOk ? 'ok' : 'bad');
    const headRule = node.querySelector('.rule-head');
    headRule.textContent = ruleText(headOk, 'Fam head attended', 'No fam head confirmed');
    headRule.classList.add(headOk ? 'ok' : 'bad');
    const advRule = node.querySelector('.rule-advertised');
    advRule.textContent = ruleText(advertisedOk, 'Advertised beforehand', 'Not confirmed as advertised');
    advRule.classList.add(advertisedOk ? 'ok' : 'bad');

    const points = node.querySelector('.points-input');
    points.value = row.status === 'approved' ? row.points_awarded : suggestedPoints(row);
    const note = node.querySelector('.note-input');
    note.value = row.reviewer_note || '';

    node.querySelector('.approve-btn').addEventListener('click', () => review(row.id, 'approved', points.value, note.value, card));
    node.querySelector('.deny-btn').addEventListener('click', () => review(row.id, 'denied', 0, note.value, card));
    list.appendChild(node);
  });
}

async function review(id, status, points, reviewer_note, card) {
  card.classList.add('saving');
  const res = await fetch(`/api/admin/submissions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, points_awarded: Number(points || 0), reviewer_note })
  });
  card.classList.remove('saving');
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    alert(data.detail || 'Could not save review.');
    return;
  }
  await loadRows();
}

document.getElementById('filterTabs').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-status]');
  if (!btn) return;
  document.querySelectorAll('#filterTabs button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentStatus = btn.dataset.status;
  renderRows();
});

searchInput.addEventListener('input', renderRows);

document.getElementById('logoutBtn').addEventListener('click', async () => {
  await fetch('/api/admin/logout', { method: 'POST' });
  location.href = '/admin/login';
});

loadRows();
