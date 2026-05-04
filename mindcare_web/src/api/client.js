/**
 * Authenticated HTTP client.
 *
 * Usage:
 *   1. AuthProvider calls configureClient() on mount to wire up token access.
 *   2. All protected API calls go through apiFetch().
 *   3. On 401 the client silently refreshes the access token and retries once.
 *   4. If refresh fails, 'auth:session-expired' is dispatched on window
 *      and AuthProvider clears the session.
 */

const _cfg = {
  getToken: null,
  setToken: null,
};

export function configureClient({ getToken, setToken }) {
  _cfg.getToken = getToken;
  _cfg.setToken = setToken;
}

async function _parseError(res) {
  const body = await res.json().catch(() => ({}));
  return new Error(body.detail || body.message || `HTTP ${res.status}`);
}

async function _tryRefresh() {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return false;

  const res = await fetch('/api/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!res.ok) {
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('access_token');
    _cfg.setToken?.(null);
    window.dispatchEvent(new Event('auth:session-expired'));
    return false;
  }

  const { access_token, refresh_token } = await res.json();
  _cfg.setToken?.(access_token);
  localStorage.setItem('access_token', access_token);
  if (refresh_token) localStorage.setItem('refresh_token', refresh_token);
  return true;
}

export async function apiFetch(url, options = {}) {
  const token = _cfg.getToken?.();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  let res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    const refreshed = await _tryRefresh();
    if (refreshed) {
      const newToken = _cfg.getToken?.();
      const retryHeaders = {
        ...headers,
        ...(newToken ? { Authorization: `Bearer ${newToken}` } : {}),
      };
      res = await fetch(url, { ...options, headers: retryHeaders });
    }
  }

  if (!res.ok) throw await _parseError(res);
  return res.json();
}
