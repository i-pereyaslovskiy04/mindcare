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

const _FALLBACK_MESSAGE = 'Ошибка запроса';
const _LOC_PREFIXES = ['body', 'query', 'path'];

/** FastAPI validation loc → читаемое имя поля ("body","email" → "email"). */
function _locField(loc) {
  if (!Array.isArray(loc) || loc.length === 0) return '';
  const parts = loc.filter((p) => !_LOC_PREFIXES.includes(p));
  return parts.join('.');
}

/**
 * Превращает тело ошибки backend в человекочитаемое сообщение.
 * - detail: string        → как есть;
 * - detail: [{msg,loc}]   → "поле: msg" объединённые "; " (FastAPI 422);
 * - message: string       → как есть;
 * - иначе                 → "HTTP <status>" или fallback.
 * Никогда не возвращает "[object Object]".
 */
export function parseErrorMessage(body, status) {
  const detail = body?.detail;

  if (typeof detail === 'string' && detail.trim()) return detail;

  if (Array.isArray(detail) && detail.length) {
    const msgs = detail
      .map((item) => {
        if (typeof item === 'string') return item;
        const msg = item?.msg;
        if (!msg) return '';
        const field = _locField(item?.loc);
        return field ? `${field}: ${msg}` : msg;
      })
      .filter(Boolean);
    if (msgs.length) return msgs.join('; ');
  }

  if (typeof body?.message === 'string' && body.message.trim()) return body.message;

  return status ? `HTTP ${status}` : _FALLBACK_MESSAGE;
}

async function _parseError(res) {
  const body = await res.json().catch(() => ({}));
  const err = new Error(parseErrorMessage(body, res.status));
  err.status = res.status;
  return err;
}

export async function apiFetch(url, options = {}) {
  const token = _cfg.getToken?.();

  // FormData: не выставляем Content-Type, браузер сам добавит boundary
  const isFormData = options.body instanceof FormData;
  const headers = {
    ...(!isFormData ? { 'Content-Type': 'application/json' } : {}),
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
