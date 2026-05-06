const API_BASE  = process.env.REACT_APP_API_URL || '/api';
const AUTH_BASE = `${API_BASE}/auth`;

const JSON_HEADERS = { 'Content-Type': 'application/json' };

async function _handleResponse(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.message || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function registerInit({ name, email, password }) {
  const res = await fetch(`${AUTH_BASE}/register/init`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ name, email, password }),
  });
  return _handleResponse(res);
}

export async function registerConfirm({ email, code }) {
  const res = await fetch(`${AUTH_BASE}/register/confirm`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, code }),
  });
  return _handleResponse(res);
}

export async function passwordResetInit({ email }) {
  const res = await fetch(`${AUTH_BASE}/password/reset/init`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ email }),
  });
  return _handleResponse(res);
}

export async function passwordResetConfirm({ email, code, newPassword }) {
  const res = await fetch(`${AUTH_BASE}/password/reset/confirm`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, code, new_password: newPassword }),
  });
  return _handleResponse(res);
}
