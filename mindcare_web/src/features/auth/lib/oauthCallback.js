/**
 * Вход через внешний провайдер (Stage Social Auth 3B) — чистые функции без React.
 *
 * Backend после callback провайдера делает 302 на фиксированный
 * `/auth/callback` и кладёт результат во fragment (он не уходит на сервер, в
 * access log и Referer):
 *   #result=login&ticket=<opaque>   — одноразовый ticket на 2 минуты;
 *   #error=<фиксированный код>      — см. FRAGMENT_ERROR_MESSAGES.
 *
 * Принимается только этот контракт: ни redirect-адресов, ни токенов
 * провайдера во fragment не бывает и они не читаются. Неизвестный код ошибки
 * пользователю не показывается — только общее сообщение.
 */

const TICKET_RE = /^[A-Za-z0-9_-]{1,128}$/; // backend: secrets.token_urlsafe, ≤128

export const FRAGMENT_ERROR_MESSAGES = Object.freeze({
  oauth_cancelled: 'Вход через Яндекс отменён.',
  oauth_failed: 'Не удалось выполнить вход через Яндекс. Попробуйте ещё раз.',
  social_registration_not_available:
    'Аккаунт Яндекс пока не привязан к MindCare. '
    + 'Вход через Яндекс доступен только для уже связанных аккаунтов.',
  account_unavailable:
    'Доступ к аккаунту сейчас недоступен. Обратитесь к администратору.',
  social_login_not_allowed: 'Вход через Яндекс для этой учётной записи недоступен.',
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

/**
 * Разбор fragment. Возвращает:
 *   { kind: 'login', ticket }  — валидный ticket;
 *   { kind: 'error', code }    — code: известный код или null (неизвестный);
 *   { kind: 'invalid' }        — fragment пуст или не по контракту.
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
  if (params.get('result') === 'login' && ticket && TICKET_RE.test(ticket)) {
    return { kind: 'login', ticket };
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

/** Сообщение для исхода, разобранного из fragment (не для 'login'). */
export function fragmentMessage(captured) {
  if (captured?.kind === 'error') {
    return captured.code ? FRAGMENT_ERROR_MESSAGES[captured.code] : GENERIC_ERROR_MESSAGE;
  }
  return INVALID_LINK_MESSAGE;
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
