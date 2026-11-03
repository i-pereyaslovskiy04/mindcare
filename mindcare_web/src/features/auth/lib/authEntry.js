/**
 * Router-state контракт канонического входа: главная `/` + AuthModal.
 *
 *   {
 *     openAuth:     'login' | 'register' | 'confirm',  // что открыть в модалке
 *     message?:     string,                 // системное сообщение над формой
 *     messageTone?: 'info' | 'error',       // закрытый список, не CSS-классы
 *   }
 *
 * Пишут: guards, истечение сессии (AuthContext), смена пароля, совместимые
 * редиректы `/login` и `/register`, терминальные ошибки OAuth callback.
 * 'confirm' — шаг подтверждения регистрации по ссылке из письма (не вкладка);
 * его открывает маршрут `/register/confirm#r=<reference>` (Home routeAuth).
 * Читает: Home (через authRequestFrom). Чистые функции без React.
 */

export const AUTH_TABS = Object.freeze(['login', 'register']);
/** Подтверждение регистрации по ссылке из письма (без вкладок «Вход | Регистрация»). */
export const AUTH_CONFIRM = 'confirm';
/**
 * Продолжение регистрации через Яндекс/VK из письма (/register/social). Только
 * маршрут (Home routeAuth), не router state: ticket — в HttpOnly cookie.
 */
export const AUTH_SOCIAL_CONTINUE = 'social';
const AUTH_ENTRIES = Object.freeze([...AUTH_TABS, AUTH_CONFIRM]);
export const MESSAGE_TONES = Object.freeze(['info', 'error']);
export const DEFAULT_MESSAGE_TONE = 'info';

/** Тон только из закрытого списка; иное значение → нейтральный 'info'. */
export function safeMessageTone(tone) {
  return MESSAGE_TONES.includes(tone) ? tone : DEFAULT_MESSAGE_TONE;
}

/**
 * Router state → { tab, message, messageTone } или null, если открывать
 * модалку не просили. Неизвестная вкладка → null; не-строковое сообщение
 * отбрасывается; неизвестный тон → 'info'.
 */
export function authRequestFrom(state) {
  const tab = AUTH_ENTRIES.includes(state?.openAuth) ? state.openAuth : null;
  if (!tab) return null;
  const message = typeof state?.message === 'string' ? state.message : '';
  return {
    tab,
    message,
    messageTone: message ? safeMessageTone(state?.messageTone) : DEFAULT_MESSAGE_TONE,
  };
}

/** Собрать router state для перехода на `/` с открытой модалкой. */
export function authEntryState(tab, message, messageTone) {
  const state = { openAuth: AUTH_ENTRIES.includes(tab) ? tab : 'login' };
  if (typeof message === 'string' && message) {
    state.message = message;
    state.messageTone = safeMessageTone(messageTone);
  }
  return state;
}

// Продолжение регистрации по ссылке из письма: /register/confirm#r=<uuid>.
// Reference — UUIDv4 выпуска кода (otp_verifications.id); лишь выбирает
// ожидающую регистрацию, без кода из письма ничего не подтверждает. Живёт
// только во fragment (не уходит на сервер при GET, не попадает в access log и
// Referer) и в памяти; в storage не сохраняется, на backend уходит только в
// теле POST.
const UUID_V4_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** location.hash → reference (UUIDv4 в нижнем регистре) или null. */
export function registrationReferenceFrom(hash) {
  const raw = typeof hash === 'string' ? hash.replace(/^#/, '') : '';
  if (!raw) return null;
  let value;
  try {
    value = new URLSearchParams(raw).get('r');
  } catch {
    return null;
  }
  return typeof value === 'string' && UUID_V4_RE.test(value) ? value.toLowerCase() : null;
}
