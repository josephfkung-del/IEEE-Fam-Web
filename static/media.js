const grid = document.getElementById('mediaGrid');
const familyFilter = document.getElementById('familyFilter');
const loadMoreBtn = document.getElementById('loadMoreBtn');
const shownCount = document.getElementById('shownCount');

let offset = 0;
let loading = false;
let shown = 0;

function escapeHtml(value = '') {
  return String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

function formatDate(value) {
  if (!value) return '';
  const d = new Date(`${value}T12:00:00`);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function eventCard(event) {
  const points = Number(event.points_awarded || 0);
  const attendees = Number(event.member_count || 0);
  return `
    <article class="media-card">
      <div class="media-photo-wrap">
        <img class="media-photo" src="/api/media/${encodeURIComponent(event.id)}/photo" alt="${escapeHtml(event.event_title)}" loading="lazy" />
        <span class="media-family-badge">${escapeHtml(event.family_name)}</span>
      </div>
      <div class="media-card-body">
        <div class="media-card-meta">
          <span>${escapeHtml(formatDate(event.event_date))}</span>
          <span>${escapeHtml(event.event_type || 'event')}</span>
        </div>
        <h2>${escapeHtml(event.event_title)}</h2>
        <p>${escapeHtml(event.description)}</p>
        <div class="media-card-footer">
          <span>${attendees} attendee${attendees === 1 ? '' : 's'}</span>
          <strong>+${points} pt${points === 1 ? '' : 's'}</strong>
        </div>
      </div>
    </article>`;
}

async function loadFamilies() {
  try {
    const res = await fetch('/api/leaderboard');
    if (!res.ok) return;
    const data = await res.json();
    (data.leaderboard || []).forEach(row => {
      const option = document.createElement('option');
      option.value = row.family_name;
      option.textContent = row.family_name;
      familyFilter.appendChild(option);
    });
  } catch (_) {}
}

async function loadEvents(reset = false) {
  if (loading) return;
  loading = true;
  loadMoreBtn.disabled = true;
  if (reset) {
    offset = 0;
    shown = 0;
    grid.innerHTML = '<div class="media-loading">Loading the fam feed…</div>';
  }

  try {
    const params = new URLSearchParams({ limit: '18', offset: String(offset) });
    if (familyFilter.value) params.set('family', familyFilter.value);
    const res = await fetch(`/api/media?${params.toString()}`);
    if (!res.ok) throw new Error('Could not load approved events');
    const data = await res.json();
    const events = data.events || [];

    if (reset) grid.innerHTML = '';
    if (!events.length && shown === 0) {
      grid.innerHTML = '<div class="media-empty panel"><strong>No approved events yet.</strong><span>Once an admin approves a submission, it will appear here.</span></div>';
    } else {
      grid.insertAdjacentHTML('beforeend', events.map(eventCard).join(''));
    }

    offset = data.next_offset || offset + events.length;
    shown += events.length;
    shownCount.textContent = String(shown);
    loadMoreBtn.hidden = !data.has_more;
  } catch (err) {
    if (reset) grid.innerHTML = `<div class="media-empty panel"><strong>Couldn't load the feed.</strong><span>${escapeHtml(err.message)}</span></div>`;
  } finally {
    loading = false;
    loadMoreBtn.disabled = false;
  }
}

familyFilter.addEventListener('change', () => loadEvents(true));
loadMoreBtn.addEventListener('click', () => loadEvents(false));

loadFamilies();
loadEvents(true);
