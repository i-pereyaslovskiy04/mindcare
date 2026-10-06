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
 *   …&step=email                          — перед кодом нужен шаг выбора email
 *                                           (VK ID: адрес провайдера — лишь
 *                                           предложение, его может не быть);
 *   #error=<фиксированный код>            — см. FRAGMENT_ERROR_MESSAGES.
 *
 * Принимается только этот контракт: ни redirect-адресов, ни токенов
 * провайдера во fragment не бывает и они не читаются. Неизвестный код ошибки
 * пользователю не показывается — только общее сообщение.
 */

const TICKET_RE = /^[A-Za-z0-9_-]{1,128}$/; // backend: secrets.token_urlsafe, ≤128

// ── провайдер ────────────────────────────────────────────────────────────────
//
// Fragment callback провайдера не называет. Чтобы тексты говорили «Яндекс» или
// «VK», кнопка запоминает ИМЯ провайдера (не секрет) в sessionStorage перед
// переходом, а страница callback читает его. Нет значения / storage недоступен
// / неизвестное имя → провайдер по умолчанию. Ни ticket, ни state, ни адрес
// сюда не пишутся.

export const PROVIDER_LABELS = Object.freeze({ yandex: 'Яндекс', vk: 'VK' });
export const DEFAULT_PROVIDER = 'yandex';
const PROVIDER_STORAGE_KEY = 'mindcare_oauth_provider';

const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);

/** Имя провайдера только из закрытого списка; иное → провайдер по умолчанию. */
export function safeProvider(provider) {
  return typeof provider === 'string' && hasOwn(PROVIDER_LABELS, provider)
    ? provider : DEFAULT_PROVIDER;
}

export function providerLabel(provider) {
  return PROVIDER_LABELS[safeProvider(provider)];
}

/** Запомнить, через какого провайдера начат вход (перед уходом со страницы). */
export function rememberOAuthProvider(provider, storage = safeSessionStorage()) {
  try {
    storage?.setItem(PROVIDER_STORAGE_KEY, safeProvider(provider));
  } catch { /* storage недоступен — тексты будут по умолчанию */ }
}

/** Провайдер, через которого был начат вход (для текстов страницы callback). */
export function recallOAuthProvider(storage = safeSessionStorage()) {
  try {
    return safeProvider(storage?.getItem(PROVIDER_STORAGE_KEY));
  } catch {
    return DEFAULT_PROVIDER;
  }
}

function safeSessionStorage() {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function buildFragmentMessages(label) {
  return Object.freeze({
    oauth_cancelled: `Вход через ${label} отменён.`,
    oauth_failed: `Не удалось выполнить вход через ${label}. Попробуйте ещё раз.`,
    // Identity провайдера не привязана, а регистрации через него нет: VK ID
    // (Stage VK-1A — только вход). Для Яндекса backend этот код больше не
    // выдаёт (Stage 4) — остаётся безопасным fallback.
    social_registration_not_available:
      `Аккаунт ${label} пока не привязан к MindCare. `
      + `Вход через ${label} доступен только для уже связанных аккаунтов.`,
    account_unavailable:
      'Доступ к аккаунту сейчас недоступен. Обратитесь к администратору.',
    social_login_not_allowed: `Вход через ${label} для этой учётной записи недоступен.`,
    // Новая identity, а провайдер не передал пригодный email: регистрации нет.
    oauth_email_required:
      `${label} ID не передал адрес электронной почты, поэтому зарегистрироваться `
      + `через ${label} не получится. Зарегистрируйтесь по email и паролю.`,
  });
}

const FRAGMENT_MESSAGES_BY_PROVIDER = Object.freeze(Object.fromEntries(
  Object.entries(PROVIDER_LABELS).map(([name, label]) => [name, buildFragmentMessages(label)]),
));

/** Тексты провайдера по умолчанию; набор КЛЮЧЕЙ — закрытый список кодов fragment. */
export const FRAGMENT_ERROR_MESSAGES = FRAGMENT_MESSAGES_BY_PROVIDER[DEFAULT_PROVIDER];

export const GENERIC_ERROR_MESSAGE = 'Не удалось выполнить вход. Попробуйте ещё раз.';
export const INVALID_LINK_MESSAGE =
  'Ссылка для входа недействительна. Начните вход заново.';
export const TOO_MANY_ATTEMPTS_MESSAGE =
  'Слишком много попыток. Попробуйте немного позже.';

const TICKET_GONE_MESSAGE =
  'Ссылка для входа устарела или уже использована. Начните вход заново.';
// Коды отказа complete, текст которых тот же, что у одноимённого кода fragment.
const COMPLETE_CODES_FROM_FRAGMENT = Object.freeze([
  'account_unavailable', 'social_login_not_allowed',
]);

const TICKET_RESULTS = Object.freeze(['login', 'registration']);

/**
 * Разбор fragment. Возвращает:
 *   { kind: 'login', ticket }                    — ticket входа;
 *   { kind: 'registration', ticket, emailStep }  — ticket регистрации;
 *                                                  emailStep — нужен шаг email;
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
    const step = params.get('step');
    if (result === 'registration') {
      // step — закрытый список: отсутствует либо ровно 'email'.
      if (step !== null && step !== 'email') return { kind: 'invalid' };
      return { kind: result, ticket, emailStep: step === 'email' };
    }
    if (step !== null) return { kind: 'invalid' };   // у входа шагов нет
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

/**
 * Сообщение для исхода, разобранного из fragment (не для ticket-исходов).
 * provider — через кого начинали вход (см. recallOAuthProvider).
 */
export function fragmentMessage(captured, provider) {
  if (captured?.kind === 'error') {
    const messages = FRAGMENT_MESSAGES_BY_PROVIDER[safeProvider(provider)];
    return captured.code ? messages[captured.code] : GENERIC_ERROR_MESSAGE;
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
export function completeErrorMessage(err, provider) {
  if (err?.status === 429) return TOO_MANY_ATTEMPTS_MESSAGE;
  const code = err?.code;
  if (code === 'oauth_ticket_invalid') return TICKET_GONE_MESSAGE;
  if (COMPLETE_CODES_FROM_FRAGMENT.includes(code)) {
    return FRAGMENT_MESSAGES_BY_PROVIDER[safeProvider(provider)][code];
  }
  return GENERIC_ERROR_MESSAGE;
}

/** Ошибка POST /oauth/{provider}/start → фиксированное сообщение. */
export function startErrorMessage(err, provider) {
  if (err?.status === 429) return TOO_MANY_ATTEMPTS_MESSAGE;
  const label = providerLabel(provider);
  if (err?.code === 'oauth_provider_unavailable') {
    return `Вход через ${label} сейчас недоступен. Войдите по email и паролю.`;
  }
  return `Не удалось начать вход через ${label}. Попробуйте ещё раз.`;
}

/** Статус страницы callback на время обмена ticket входа. */
export function loginStatusMessage(provider) {
  return `Выполняем вход через ${providerLabel(provider)}…`;
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

function buildRegistrationMessages(label) {
  return Object.freeze({
    email_already_exists:
      'Аккаунт с таким email уже существует. Войдите по email и паролю.',
    oauth_identity_already_linked:
      `Этот аккаунт ${label} уже привязан к MindCare. Нажмите «${label}» ещё раз, чтобы войти.`,
    oauth_ticket_invalid:
      `Время на завершение регистрации истекло. Начните заново через ${label}.`,
    email_delivery_failed: 'Не удалось отправить письмо. Попробуйте позже.',
    internal_error: 'Не удалось завершить регистрацию. Обратитесь в поддержку.',
    consent_required: 'Необходимо принять политику персональных данных.',
    email_required: 'Укажите адрес электронной почты.',
    email_invalid: 'Введите корректный адрес электронной почты.',
    email_not_changeable: 'Адрес электронной почты для этой регистрации изменить нельзя.',
    rate_limited: TOO_MANY_ATTEMPTS_MESSAGE,
  });
}

const REGISTRATION_MESSAGES_BY_PROVIDER = Object.freeze(Object.fromEntries(
  Object.entries(PROVIDER_LABELS).map(
    ([name, label]) => [name, buildRegistrationMessages(label)],
  ),
));

// Коды, для которых backend отдаёт собственный фиксированный русский текст с
// полезной деталью (остаток попыток, секунды до повторной отправки, отказ по
// домену почты — тот же текст, что у обычной регистрации).
const REGISTRATION_SERVER_TEXT_CODES = Object.freeze([
  'otp_invalid', 'otp_expired', 'otp_cooldown', 'domain_not_allowed',
]);

/** Коды, после которых этот ticket уже не завершит регистрацию. */
const REGISTRATION_TERMINAL_CODES = Object.freeze([
  'oauth_ticket_invalid', 'oauth_identity_already_linked',
]);

/**
 * Ошибка init/confirm регистрации → текст для пользователя. Неизвестный код
 * или ответ без кода (в т.ч. 422 валидации) — общее сообщение, без текста
 * сервера.
 */
export function registrationErrorMessage(err, provider) {
  const code = err?.code;
  if (typeof code === 'string') {
    const messages = REGISTRATION_MESSAGES_BY_PROVIDER[safeProvider(provider)];
    if (hasOwn(messages, code)) return messages[code];
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

/**
 * true — продолжать с этим ticket бессмысленно, нужен новый вход через
 * провайдера. Занятый email терминален только при ФИКСИРОВАННОМ адресе
 * (Яндекс): там ticket сожжён. Если адрес можно изменить (emailEditable — VK),
 * это исправимая ошибка: пользователь указывает другой адрес тем же ticket.
 */
export function isRegistrationTerminal(err, { emailEditable = false } = {}) {
  const code = err?.code;
  if (typeof code !== 'string') return false;
  if (REGISTRATION_TERMINAL_CODES.includes(code)) return true;
  return code === 'email_already_exists' && !emailEditable;
}
