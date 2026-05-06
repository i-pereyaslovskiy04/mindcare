/**
 * Authenticated HTTP client.
 *
 * Использует session_token из AuthContext.
 * При 401 — сессия истекла, уведомляем AuthProvider через событие.
 */

const _cfg = { getToken: null };

export function configureClient({ getToken }) {
  _cfg.getToken = getToken;
}

async function _parseError(res) {
  const body = await res.json().catch(() => ({}));
  return new Error(body.detail || body.message || `HTTP ${res.status}`);
}

export async function apiFetch(url, options = {}) {
  const token = _cfg.getToken?.();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    window.dispatchEvent(new Event('auth:session-expired'));
  }

  if (!res.ok) throw await _parseError(res);
  return res.json();
}
