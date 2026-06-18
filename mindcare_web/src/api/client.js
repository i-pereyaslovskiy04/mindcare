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

/**
 * Сохраняет файл на диск пользователя без top-level blob: navigation.
 *
 * Primary path (Chromium): File System Access API — showSaveFilePicker.
 *   Вызов showSaveFilePicker должен происходить как первый await в функции,
 *   чтобы пикер открылся внутри user activation window (до HTTP-запроса).
 *
 * Fallback (Firefox, Safari, older Chromium): anchor + blob URL.
 *   Blob оборачивается в application/octet-stream, чтобы браузер не пытался
 *   открыть документ inline. revokeObjectURL отложен на 1000 ms.
 *
 * fetchFn — async () => Blob   (вызывается ВНУТРИ saveBlobToDisk)
 * filename — предлагаемое имя файла или null
 *
 * Throws AbortError, если пользователь отменил save-диалог (не ошибка).
 */
export async function saveBlobToDisk(fetchFn, filename) {
  const safeName = filename || 'файл';

  if (typeof window?.showSaveFilePicker === 'function') {
    let fileHandle = null;
    try {
      fileHandle = await window.showSaveFilePicker({ suggestedName: safeName });
    } catch (err) {
      if (err?.name === 'AbortError') {
        throw err;
      }
      // NotAllowedError, SecurityError или другая нефатальная ошибка → fallback.
    }

    if (fileHandle) {
      const blob = await fetchFn();
      const writable = await fileHandle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    }
  }

  // Fallback: anchor + blob URL (Firefox, Safari, older Chromium).
  const blob = await fetchFn();
  // Оборачиваем в octet-stream — браузер не откроет документ inline.
  const dlBlob = new Blob([blob], { type: 'application/octet-stream' });
  const url = URL.createObjectURL(dlBlob);
  const a = document.createElement('a');
  a.href = url;
  a.setAttribute('download', safeName);
  a.rel = 'noopener noreferrer';
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Задержка revoke: браузер должен успеть начать чтение Blob до отзыва URL.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Скачивает ресурс как Blob с Auth-заголовком.
 * Возвращает { blob, filename } — filename из Content-Disposition или null.
 */
export async function apiFetchBlob(url, options = {}) {
  const token = _cfg.getToken?.();
  const headers = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    window.dispatchEvent(new Event('auth:session-expired'));
  }
  if (!res.ok) throw await _parseError(res);
  const blob = await res.blob();
  let filename = null;
  const cd = res.headers.get('Content-Disposition') || '';
  // RFC 5987: filename*=UTF-8''<percent-encoded> (backend использует этот формат)
  const m5987 = cd.match(/filename\*\s*=\s*UTF-8''([^;\s]+)/i);
  if (m5987) {
    try { filename = decodeURIComponent(m5987[1]); } catch { filename = m5987[1]; }
  } else {
    // Fallback: filename="value" или filename=value
    const mLegacy = cd.match(/filename\s*=\s*"([^"]+)"/i) || cd.match(/filename\s*=\s*([^;\s,\n]+)/i);
    if (mLegacy) filename = mLegacy[1].trim();
  }
  return { blob, filename };
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
