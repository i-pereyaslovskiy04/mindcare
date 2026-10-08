/**
 * Подтверждение статуса студента ДонГУ (ADR-029) — подписи и правила UI.
 *
 * Статус «Студент ДонГУ подтверждён» — НЕ роль: подпись роли по-прежнему
 * берётся из shared/lib/roles.js («Пользователь»). Здесь только статусы заявки.
 * Факультеты на клиенте не зашиты — они приходят с backend.
 */

/** Якорь раздела в настройках; на него ведёт ссылка из system-сообщения. */
export const STUDENT_VERIFICATION_ANCHOR = 'student-verification';
export const STUDENT_VERIFICATION_SETTINGS_PATH = `/student/settings#${STUDENT_VERIFICATION_ANCHOR}`;

export const VERIFIED_BADGE_LABEL = 'Студент ДонГУ подтверждён';

export const VERIFICATION_STATUS_LABELS = {
  not_submitted: 'Не подтверждено',
  pending:       'На проверке',
  approved:      'Подтверждено',
  rejected:      'Отклонено',
};

export const VERIFICATION_STATUS_TONES = {
  not_submitted: 'neutral',
  pending:       'warning',
  approved:      'success',
  rejected:      'error',
};

export function verificationStatusLabel(status) {
  return VERIFICATION_STATUS_LABELS[status] ?? VERIFICATION_STATUS_LABELS.not_submitted;
}

export function verificationStatusTone(status) {
  return VERIFICATION_STATUS_TONES[status] ?? 'neutral';
}

/** Фиксированные тексты по стабильному err.code (код пользователю не показывается). */
export const VERIFICATION_ERROR_MESSAGES = {
  verification_not_allowed:     'Подтверждение доступно только пользователю без служебных ролей.',
  impersonation_forbidden:      'Недоступно при входе под именем пользователя.',
  verification_pending_exists:  'Заявка уже отправлена и находится на проверке.',
  already_verified:             'Статус студента ДонГУ уже подтверждён.',
  account_inactive:             'Аккаунт пользователя отключён — подтвердить заявку нельзя.',
  verification_not_found:       'Заявка не найдена.',
  self_review_forbidden:        'Нельзя проверять собственную заявку.',
  reviewer_not_allowed:         'Недостаточно прав для проверки заявок.',
  verification_already_decided: 'По заявке уже принято другое решение.',
};

export function verificationErrorMessage(err, fallback = 'Не удалось выполнить действие') {
  return (err?.code && VERIFICATION_ERROR_MESSAGES[err.code]) || err?.message || fallback;
}

/**
 * Self-service доступен только «чистому» пользователю (активные роли ровно
 * student) вне режима «под именем». Staff получают student неявно (ADR-024);
 * backend всё равно проверяет авторитетно.
 */
export function canUseVerificationSelfService(roles, isImpersonating) {
  const list = Array.isArray(roles) ? roles : [];
  return list.length === 1 && list[0] === 'student' && !isImpersonating;
}

const DATE_FMT = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

const DATE_TIME_FMT = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

function toDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Дата по МСК; пусто/невалидно → «—». */
export function formatVerificationDate(value) {
  const date = toDate(value);
  return date ? DATE_FMT.format(date) : '—';
}

export function formatVerificationDateTime(value) {
  const date = toDate(value);
  return date ? DATE_TIME_FMT.format(date) : '—';
}
