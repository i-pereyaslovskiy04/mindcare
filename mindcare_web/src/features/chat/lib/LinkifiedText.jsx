/**
 * Безопасный frontend-only linkify для plaintext-сообщений.
 *
 * Безопасность:
 *   - НЕ используется dangerouslySetInnerHTML — текст рендерится как React-узлы,
 *     поэтому любой HTML/JS (<script>…</script>) показывается как обычный текст
 *     и не исполняется;
 *   - кликабельны только ссылки на http:// и https://;
 *   - href ставится исключительно для совпавшего URL, ссылки открываются с
 *     target="_blank" + rel="noopener noreferrer";
 *   - backend и хранение не затрагиваются (HTML в БД не пишется).
 */

const URL_RE = /(https?:\/\/[^\s<>"']+)/g;
// Хвостовая пунктуация, которую не считаем частью ссылки.
const TRAILING_RE = /[),.;:!?]+$/;

export default function LinkifiedText({ text }) {
  if (!text) return null;

  const parts = [];
  let lastIndex = 0;
  let match;
  URL_RE.lastIndex = 0;

  while ((match = URL_RE.exec(text)) !== null) {
    const raw = match[0];
    const start = match.index;

    if (start > lastIndex) parts.push(text.slice(lastIndex, start));

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

  if (lastIndex < text.length) parts.push(text.slice(lastIndex));

  return <>{parts}</>;
}
