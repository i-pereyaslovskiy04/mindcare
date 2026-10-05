/**
 * Вход и регистрация через внешний провайдер (Stage Social Auth 3B/4) — чистые
 * функции без React.
 *
 * Backend после callback провайдера делает 302 на фиксированный
 * `/auth/callback` и кладёт результат во fragment (он не уходит на сервер, в
 * access log и Referer):
 *   #result=login&ticket=<opaque>         — identity уже привязана: одноразовый
 *                                           ticket входа на 2 минуты;
 *   #result=registration&ticket=<opaque>  — identity новая: ticket регистрации
 *                                           на 30 минут (email и имя — из
 *                                           профиля провайдера; код из письма);
 *   #error=<фиксированный код>            — см. FRAGMENT_ERROR_MESSAGES.
 *
 * Принимается только этот контракт: ни redirect-адресов, ни токенов
 * провайдера во fragment не бывает и они не читаются. Неизвестный код ошибки
 * пользователю не показывается — только общее сообщение.
 */

const TICKET_RE = /^[A-Za-z0-9_-]{1,128}$/; // backend: secrets.token_urlsafe, ≤128

export const FRAGMENT_ERROR_MESSAGES = Object.freeze({
  oauth_cancelled: 'Вход через Яндекс отменён.',
  oauth_failed: 'Не удалось выполнить вход через Яндекс. Попробуйте ещё раз.',
  // Legacy (до Stage 4 backend отдавал этот код для неизвестной identity).
  // Сейчас backend его штатно не выдаёт — оставлен как безопасный fallback.
  social_registration_not_available:
    'Аккаунт Яндекс пока не привязан к MindCare. '
    + 'Вход через Яндекс доступен только для уже связанных аккаунтов.',
  account_unavailable:
    'Доступ к аккаунту сейчас недоступен. Обратитесь к администратору.',
  social_login_not_allowed: 'Вход через Яндекс для этой учётной записи недоступен.',
  // Новая identity, а Яндекс не передал пригодный email: регистрации нет.
  oauth_email_required:
    'Яндекс ID не передал адрес электронной почты, поэтому зарегистрироваться '
    + 'через Яндекс не получится. Зарегистрируйтесь по email и паролю.',
});

export const GENERIC_ERROR_MESSAGE = 'Не удалось выполнить вход. Попробуйте ещё раз.';
export const INVALID_LINK_MESSAGE =
  'Ссылка для входа недействительна. Начните вход заново.';
export const TOO_MANY_ATTEMPTS_MESSAGE =
  'Слишком много попыток. Попробуйте немного позже.';

const COMPLETE_ERROR_MESSAGES = Object.freeze({
  oauth_ticket_invalid:
    'Ссылка для входа устарела или уже использована. Начните вход заново.',
  account_unavailable: FRAGMENT_ERROR_MESSAGES.account_unavailable,
  social_login_not_allowed: FRAGMENT_ERROR_MESSAGES.social_login_not_allowed,
});

const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);

const TICKET_RESULTS = Object.freeze(['login', 'registration']);

/**
 * Разбор fragment. Возвращает:
 *   { kind: 'login', ticket }         — ticket входа;
 *   { kind: 'registration', ticket }  — ticket регистрации;
 *   { kind: 'error', code }           — code: известный код или null (неизвестный);
 *   { kind: 'invalid' }               — fragment пуст или не по контракту.
 */
export function parseCallbackFragment(hash) {
  const raw = typeof hash === 'string' ? hash.replace(/^#/, '') : '';
  if (!raw) return { kind: 'invalid' };

  let params;
  try {
    params = new URLSearchParams(raw);
  } catch {
    return { kind: 'invalid' };
  }

  const error = params.get('error');
  if (error !== null) {
    return {
      kind: 'error',
      code: hasOwn(FRAGMENT_ERROR_MESSAGES, error) ? error : null,
    };
  }

  const ticket = params.get('ticket');
  const result = params.get('result');
  if (TICKET_RESULTS.includes(result) && ticket && TICKET_RE.test(ticket)) {
    return { kind: result, ticket };
  }
  return { kind: 'invalid' };
}

/**
 * Убирает fragment (ticket/код) из адресной строки и истории — синхронно,
 * replaceState, без новой записи истории и без перезагрузки. State записи
 * истории (ключ React Router) сохраняется.
 */
export function scrubCallbackFragment(win = window) {
  const { pathname, search } = win.location;
  win.history.replaceState(win.history.state, '', `${pathname}${search}`);
}

/** Сообщение для исхода, разобранного из fragment (не для ticket-исходов). */
export function fragmentMessage(captured) {
  if (captured?.kind === 'error') {
    return captured.code ? FRAGMENT_ERROR_MESSAGES[captured.code] : GENERIC_ERROR_MESSAGE;
  }
  return INVALID_LINK_MESSAGE;
}

/**
 * Тон сообщения для AuthModal по исходу fragment: отмена на странице Яндекса —
 * осознанное действие пользователя ('info'); всё остальное — ошибка ('error').
 */
export function fragmentTone(captured) {
  return captured?.kind === 'error' && captured.code === 'oauth_cancelled' ? 'info' : 'error';
}

/** Ошибка POST /oauth/complete → фиксированное сообщение (без текста сервера). */
export function completeErrorMessage(err) {
  if (err?.status === 429) return TOO_MANY_ATTEMPTS_MESSAGE;
  const code = err?.code;
  if (typeof code === 'string' && hasOwn(COMPLETE_ERROR_MESSAGES, code)) {
    return COMPLETE_ERROR_MESSAGES[code];
  }
  return GENERIC_ERROR_MESSAGE;
}

/** Ошибка POST /oauth/{provider}/start → фиксированное сообщение. */
export function startErrorMessage(err) {
  if (err?.status === 429) return TOO_MANY_ATTEMPTS_MESSAGE;
  if (err?.code === 'oauth_provider_unavailable') {
    return 'Вход через Яндекс сейчас недоступен. Войдите по email и паролю.';
  }
  return 'Не удалось начать вход через Яндекс. Попробуйте ещё раз.';
}

/** authorize_url принимается только как абсолютный https-адрес. */
export function isSafeAuthorizeUrl(url) {
  if (typeof url !== 'string' || !url) return false;
  try {
    return new URL(url).protocol === 'https:';
  } catch {
    return false;
  }
}

/**
 * Top-level переход на страницу провайдера (не popup). Отдельная функция —
 * чтобы тесты могли подменить навигацию jsdom.
 */
export function navigateToProvider(url) {
  window.location.assign(url);
}

// ── регистрация через провайдера (Stage Social Auth 4) ───────────────────────

export const REGISTRATION_GENERIC_MESSAGE =
  'Не удалось завершить регистрацию. Попробуйте ещё раз.';

const REGISTRATION_ERROR_MESSAGES = Object.freeze({
  email_already_exists:
    'Аккаунт с таким email уже существует. Войдите по email и паролю.',
  oauth_identity_already_linked:
    'Этот аккаунт Яндекс уже привязан к MindCare. Нажмите «Яндекс» ещё раз, чтобы войти.',
  oauth_ticket_invalid:
    'Время на завершение регистрации истекло. Начните заново через Яндекс.',
  email_delivery_failed: 'Не удалось отправить письмо. Попробуйте позже.',
  internal_error: 'Не удалось завершить регистрацию. Обратитесь в поддержку.',
  consent_required: 'Необходимо принять политику персональных данных.',
  rate_limited: TOO_MANY_ATTEMPTS_MESSAGE,
});

// Коды, для которых backend отдаёт собственный фиксированный русский текст с
// полезной деталью (остаток попыток, секунды до повторной отправки).
const REGISTRATION_SERVER_TEXT_CODES = Object.freeze([
  'otp_invalid', 'otp_expired', 'otp_cooldown',
]);

/** Коды, после которых этот ticket уже не завершит регистрацию. */
const REGISTRATION_TERMINAL_CODES = Object.freeze([
  'oauth_ticket_invalid', 'oauth_identity_already_linked', 'email_already_exists',
]);

/**
 * Ошибка init/confirm регистрации → текст для пользователя. Неизвестный код
 * или ответ без кода (в т.ч. 422 валидации) — общее сообщение, без текста
 * сервера.
 */
export function registrationErrorMessage(err) {
  const code = err?.code;
  if (typeof code === 'string') {
    if (hasOwn(REGISTRATION_ERROR_MESSAGES, code)) return REGISTRATION_ERROR_MESSAGES[code];
    if (
      REGISTRATION_SERVER_TEXT_CODES.includes(code)
      && typeof err.message === 'string' && err.message
    ) {
      return err.message;
    }
  }
  if (err?.status === 429) return TOO_MANY_ATTEMPTS_MESSAGE;
  return REGISTRATION_GENERIC_MESSAGE;
}

/** true — продолжать с этим ticket бессмысленно, нужен новый вход через Яндекс. */
export function isRegistrationTerminal(err) {
  return typeof err?.code === 'string' && REGISTRATION_TERMINAL_CODES.includes(err.code);
}
