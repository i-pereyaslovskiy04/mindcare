/**
 * Безопасный frontend-only linkify для plaintext-сообщений.
 *
 * Безопасность:
 *   - НЕ используется dangerouslySetInnerHTML — текст рендерится как React-узлы,
 *     поэтому любой HTML/JS (<script>…</script>) показывается как обычный текст
 *     и не исполняется;
 *   - внешними ссылками становятся только http:// и https://;
 *   - href ставится исключительно для совпавшего URL, внешние ссылки
 *     открываются с target="_blank" + rel="noopener noreferrer";
 *   - backend и хранение не затрагиваются (HTML в БД не пишется).
 *
 * Внутренние ссылки (ADR-029): только при allowInternalLinks (MessageBubble
 * включает его ТОЛЬКО для system-сообщений MindCare) и только для путей из
 * ТОЧНОГО allowlist INTERNAL_LINKS. Путь должен стоять отдельным словом:
 * «/student/settings#student-verification-x», «x/student/…», «//host/…» и
 * любые иные относительные пути остаются текстом. Ссылка рендерится через
 * router <Link> (переход внутри SPA, без перезагрузки) с подписью из allowlist.
 */
import { Link } from 'react-router-dom';

const URL_RE = /(https?:\/\/[^\s<>"']+)/g;
// Хвостовая пунктуация, которую не считаем частью ссылки.
const TRAILING_RE = /[),.;:!?]+$/;

export const INTERNAL_LINKS = Object.freeze({
  '/student/settings#student-verification': 'Подтверждение студента ДонГУ',
});

function escapeRe(value) {
  return value.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
}

// Путь — отдельное слово: слева начало строки, пробел или «(»; справа конец
// строки, пробел или хвостовая пунктуация. Lookbehind не используется
// (поддержка старых Safari) — левый разделитель захватывается группой.
const INTERNAL_RE = new RegExp(
  `(^|[\\s(])(${Object.keys(INTERNAL_LINKS).map(escapeRe).join('|')})(?=$|[\\s),.;:!?])`,
  'g',
);

function pushInternal(parts, segment, keyBase) {
  let last = 0;
  let match;
  INTERNAL_RE.lastIndex = 0;
  while ((match = INTERNAL_RE.exec(segment)) !== null) {
    const [, prefix, path] = match;
    const start = match.index + prefix.length;
    if (start > last) parts.push(segment.slice(last, start));
    parts.push(
      <Link key={`${keyBase}-${start}`} to={path}>{INTERNAL_LINKS[path]}</Link>,
    );
    last = start + path.length;
  }
  if (last < segment.length) parts.push(segment.slice(last));
}

export default function LinkifiedText({ text, allowInternalLinks = false }) {
  if (!text) return null;

  const parts = [];
  const pushText = (segment, keyBase) => {
    if (!segment) return;
    if (allowInternalLinks) pushInternal(parts, segment, keyBase);
    else parts.push(segment);
  };

  let lastIndex = 0;
  let match;
  URL_RE.lastIndex = 0;

  while ((match = URL_RE.exec(text)) !== null) {
    const raw = match[0];
    const start = match.index;

    if (start > lastIndex) pushText(text.slice(lastIndex, start), `t${lastIndex}`);

    let href = raw;
    let trailing = '';
    const t = href.match(TRAILING_RE);
    if (t) {
      trailing = t[0];
      href = href.slice(0, -trailing.length);
    }

    parts.push(
      <a key={start} href={href} target="_blank" rel="noopener noreferrer">
        {href}
      </a>,
    );
    if (trailing) parts.push(trailing);

    lastIndex = start + raw.length;
  }

  if (lastIndex < text.length) pushText(text.slice(lastIndex), `t${lastIndex}`);

  return <>{parts}</>;
}
