/**
 * Allowlist внутренних ссылок system-сообщений (ADR-029) и разбор путей в
 * тексте. Без зависимости от router: используется LinkifiedText (ссылки в
 * Messenger) и текстовым превью колокольчика шапки (features/bell).
 */

export const INTERNAL_LINKS = Object.freeze({
  '/student/settings#student-verification': 'Подтверждение студента ДонГУ',
});

function escapeRe(value) {
  return value.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
}

// Путь — отдельное слово: слева начало строки, пробел или «(»; справа конец
// строки, пробел или хвостовая пунктуация. Lookbehind не используется
// (поддержка старых Safari) — левый разделитель захватывается группой.
export const INTERNAL_RE = new RegExp(
  `(^|[\\s(])(${Object.keys(INTERNAL_LINKS).map(escapeRe).join('|')})(?=$|[\\s),.;:!?])`,
  'g',
);

/**
 * Текст без сырых внутренних путей: путь из allowlist заменяется его подписью
 * (для превью, где ссылка не рендерится). Остальной текст не меняется.
 */
export function replaceInternalLinks(text) {
  if (!text) return '';
  return text.replace(INTERNAL_RE, (match, prefix, path) => `${prefix}${INTERNAL_LINKS[path]}`);
}
