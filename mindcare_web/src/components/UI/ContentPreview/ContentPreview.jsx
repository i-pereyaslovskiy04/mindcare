import DOMPurify from 'dompurify';
import Modal from '../../Modal/Modal';
import styles from './ContentPreview.module.css';

/**
 * Форматирует ISO-дату в читаемый русский вид.
 * Например: "2026-05-29T10:00:00Z" → "29 мая 2026"
 */
function formatDate(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

/**
 * ContentPreview — модальный предпросмотр статьи или новости.
 *
 * Принимает props:
 *   open        — показывать ли модалку
 *   onClose     — закрыть модалку
 *   title       — заголовок
 *   content     — HTML от TipTap (санируется через DOMPurify перед рендером)
 *   coverUrl    — URL обложки (или null)
 *   excerpt     — краткое описание (только у материалов)
 *   tags        — массив строк: ['Тревога', 'Стресс']
 *   categories  — массив строк: ['Статья', 'Вебинар'] (только у материалов)
 *   publishedAt — ISO-дата публикации (или null для черновиков)
 *   authorName  — имя автора (или null)
 */
export default function ContentPreview({
  open,
  onClose,
  title,
  content,
  coverUrl,
  excerpt,
  tags = [],
  categories = [],
  publishedAt,
  authorName,
}) {
  // sanitizedHtml — очищенный HTML, безопасный для dangerouslySetInnerHTML.
  // DOMPurify удаляет <script>, onerror= и другие XSS-векторы.
  const sanitizedHtml = content ? DOMPurify.sanitize(content) : '';

  const dateLabel   = formatDate(publishedAt);
  const isDraft     = !publishedAt;

  return (
    // wide — широкая модалка (780px), удобнее для чтения длинного текста
    <Modal open={open} onClose={onClose} wide zIndex={2100}>
      <div className={styles.wrap}>

        {/* Плашка «Черновик» — видна только если дата публикации не задана */}
        {isDraft && (
          <div className={styles.draftBadge}>Черновик — не опубликовано</div>
        )}

        {/* Обложка — если загружена. object-fit: cover обрезает по пропорции */}
        {coverUrl && (
          <div className={styles.cover}>
            <img src={coverUrl} alt={title} className={styles.coverImg} />
          </div>
        )}

        <div className={styles.inner}>
          {/* Категории (тип) — только у материалов */}
          {categories.length > 0 && (
            <div className={styles.meta}>
              {categories.map(c => (
                <span key={c} className={styles.category}>{c}</span>
              ))}
            </div>
          )}

          {/* Заголовок */}
          <h1 className={styles.title}>{title || 'Без заголовка'}</h1>

          {/* Краткое описание — только у материалов */}
          {excerpt && <p className={styles.excerpt}>{excerpt}</p>}

          {/* Строка мета-данных: дата, автор */}
          {(dateLabel || authorName) && (
            <div className={styles.metaRow}>
              {dateLabel && <span>{dateLabel}</span>}
              {dateLabel && authorName && (
                <span className={styles.dot} aria-hidden="true">·</span>
              )}
              {authorName && <span>{authorName}</span>}
            </div>
          )}

          {/* Теги */}
          {tags.length > 0 && (
            <div className={styles.tags}>
              {tags.map(t => (
                <span key={t} className={styles.tag}>{t}</span>
              ))}
            </div>
          )}

          {/* Основной контент — HTML от TipTap.
              dangerouslySetInnerHTML нужен чтобы браузер интерпретировал
              теги <p>, <h2>, <ul> и т.д. из редактора.
              sanitizedHtml уже очищен DOMPurify выше. */}
          {sanitizedHtml ? (
            <div
              className={styles.content}
              dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
            />
          ) : (
            <p className={styles.empty}>Содержимое не добавлено.</p>
          )}
        </div>
      </div>
    </Modal>
  );
}
