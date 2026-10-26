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
 * редиректы `/login` и `/register`, `/register/confirm` (кнопка «Продолжить
 * регистрацию» из письма; 'confirm' — шаг подтверждения по email и коду, не
 * вкладка), терминальные ошибки OAuth callback.
 * Читает: Home (через authRequestFrom). Чистые функции без React.
 */

export const AUTH_TABS = Object.freeze(['login', 'register']);
/** Подтверждение регистрации по email и коду (без вкладок «Вход | Регистрация»). */
export const AUTH_CONFIRM = 'confirm';
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
