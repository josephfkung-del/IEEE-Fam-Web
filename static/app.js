const form = document.getElementById('submissionForm');
const photoInput = document.getElementById('photoInput');
const preview = document.getElementById('photoPreview');
const prompt = document.getElementById('uploadPrompt');
const message = document.getElementById('formMessage');
const submitBtn = document.getElementById('submitBtn');
let compressedPhoto = null;

function setMessage(text, kind = '') {
  message.textContent = text;
  message.className = `form-message ${kind}`;
}

function compressImage(file, maxWidth = 1400, quality = 0.78) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = () => {
      const img = new Image();
      img.onerror = reject;
      img.onload = () => {
        const scale = Math.min(1, maxWidth / img.width);
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL('image/jpeg', quality));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

photoInput.addEventListener('change', async () => {
  const file = photoInput.files?.[0];
  if (!file) return;
  if (!file.type.startsWith('image/')) {
    setMessage('Please choose an image file.', 'error');
    photoInput.value = '';
    return;
  }
  setMessage('Preparing photo…');
  try {
    compressedPhoto = await compressImage(file);
    preview.src = compressedPhoto;
    preview.hidden = false;
    prompt.hidden = true;
    setMessage('Photo ready.', 'success');
  } catch {
    setMessage('Could not read that photo. Try another image.', 'error');
  }
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!compressedPhoto) {
    setMessage('Please upload a proof photo.', 'error');
    return;
  }

  const data = new FormData(form);
  const payload = {
    family_name: data.get('family_name'),
    submitter_name: data.get('submitter_name'),
    event_title: data.get('event_title'),
    event_date: data.get('event_date'),
    event_type: data.get('event_type'),
    member_count: Number(data.get('member_count') || 0),
    description: data.get('description'),
    fam_head_present: data.get('fam_head_present') === 'on',
    advertised_beforehand: data.get('advertised_beforehand') === 'on',
    photo_data: compressedPhoto,
    photo_filename: photoInput.files?.[0]?.name || 'photo.jpg',
    photo_mime: 'image/jpeg'
  };

  submitBtn.disabled = true;
  submitBtn.textContent = 'Submitting…';
  setMessage('Sending your event to the review queue…');
  try {
    const res = await fetch('/api/submissions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Submission failed');
    form.reset();
    compressedPhoto = null;
    preview.hidden = true;
    preview.src = '';
    prompt.hidden = false;
    setMessage('Submitted! Your event is now waiting for admin review.', 'success');
    loadLeaderboard();
  } catch (err) {
    setMessage(err.message || 'Something went wrong. Please try again.', 'error');
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = 'Submit event <span>→</span>';
  }
});

async function loadLeaderboard() {
  const el = document.getElementById('leaderboard');
  try {
    const res = await fetch('/api/leaderboard');
    const data = await res.json();
    const rows = data.leaderboard || [];
    if (!rows.length) {
      el.innerHTML = '<div class="empty-state">No approved events yet.</div>';
      return;
    }
    el.innerHTML = rows.slice(0, 8).map((row, i) => `
      <div class="leader-row">
        <span class="rank">${i + 1}</span>
        <span class="leader-family">${escapeHtml(row.family_name)}</span>
        <strong>${row.points} pts</strong>
      </div>`).join('');
  } catch {
    el.innerHTML = '<div class="empty-state">Leaderboard unavailable.</div>';
  }
}

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value ?? '';
  return div.innerHTML;
}

loadLeaderboard();
