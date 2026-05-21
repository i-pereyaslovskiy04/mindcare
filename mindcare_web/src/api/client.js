/**
 * Base HTTP client.
 *
 * Single source for all fetch calls.
 * - Injects Authorization: Bearer <token> when a session exists.
 *- On 401: dispatches auth:session-expired so AuthContext can clear state.
 */

const _cfg = { getToken: null };

/** Called once by AuthProvider to wire in the token getter. */
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
  if (res.status === 204) return null;
  return res.json();
}
