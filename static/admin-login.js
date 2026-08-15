const form = document.getElementById('loginForm');
const msg = document.getElementById('loginMessage');
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  msg.textContent = 'Signing in…';
  msg.className = 'form-message';
  const password = document.getElementById('password').value;
  const res = await fetch('/api/admin/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password })
  });
  if (res.ok) {
    location.href = '/admin';
    return;
  }
  const data = await res.json().catch(() => ({}));
  msg.textContent = data.detail || 'Incorrect password.';
  msg.className = 'form-message error';
});
