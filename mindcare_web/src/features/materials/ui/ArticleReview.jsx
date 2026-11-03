import { useId, useState } from 'react';
import Modal from '../../../components/Modal/Modal';
import Button from '../../../components/UI/Button/Button';
import ContentPreview from '../../../components/UI/ContentPreview/ContentPreview';
import ConfirmDialog from '../../assignments/ui/ConfirmDialog';
import useArticleReview from '../hooks/useArticleReview';
import { formatMaterialDate } from '../lib/normalizeArticle';
import dialogStyles from '../../assignments/ui/ConfirmDialog.module.css';
import styles from './ArticleReview.module.css';

const COMMENT_MAX = 2000;

function ReturnDialog({ article, loading, onConfirm, onClose }) {
  const id = useId();
  const [comment, setComment] = useState('');
  return (
    <Modal open onClose={loading ? () => {} : onClose} ariaLabel="Вернуть на доработку" zIndex={2200}>
      <form
        className={dialogStyles.body}
        onSubmit={(e) => { e.preventDefault(); onConfirm(comment.trim()); }}
        noValidate
      >
        <h2 className={dialogStyles.title}>Вернуть на доработку</h2>
        <p className={dialogStyles.text}>
          «{article.title}» вернётся автору со статусом «На доработке».
        </p>
        <div className={styles.field}>
          <label htmlFor={`${id}-comment`} className={styles.label}>
            Комментарий автору (необязательно)
          </label>
          <textarea
            id={`${id}-comment`}
            className={styles.textarea}
            value={comment}
            onChange={e => setComment(e.target.value)}
            maxLength={COMMENT_MAX}
            rows={4}
            aria-describedby={`${id}-counter`}
            disabled={loading}
          />
          <span id={`${id}-counter`} className={styles.counter}>{comment.length} / {COMMENT_MAX}</span>
        </div>
        <div className={dialogStyles.actions}>
          <Button type="button" variant="secondary" onClick={onClose} disabled={loading}>Отмена</Button>
          <Button type="submit" variant="primary" loading={loading}>Вернуть</Button>
        </div>
      </form>
    </Modal>
  );
}

/**
 * Очередь модерации статей психологов (ADR-034): supervisor и admin.
 * Предпросмотр полного текста (DOMPurify в ContentPreview), публикация с
 * подтверждением, возврат на доработку с комментарием (виден только автору).
 */
export default function ArticleReview() {
  const review = useArticleReview();
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(null);
  const [confirmPublish, setConfirmPublish] = useState(null);
  const [returning, setReturning] = useState(null);

  async function openPreview(item) {
    setPreviewError(null);
    setLoadingPreview(item.uuid);
    try {
      setPreview(await review.loadPreview(item.uuid));
    } catch {
      setPreviewError({ uuid: item.uuid, message: 'Не удалось открыть материал. Возможно, его уже проверили.' });
      review.reload();
    } finally {
      setLoadingPreview(null);
    }
  }

  async function doPublish() {
    const item = confirmPublish;
    if (!item) return;
    await review.publish(item.uuid);
    setConfirmPublish(null);
  }

  async function doReturn(comment) {
    const item = returning;
    if (!item) return;
    await review.sendBack(item.uuid, comment);
    setReturning(null);
  }

  const firstLoad = review.loading && review.items.length === 0;

  return (
    <div className={styles.wrap}>
      {firstLoad && <p className={styles.state} role="status">Загружаем очередь…</p>}
      {review.error && (
        <div className={styles.errorBox} role="alert">
          <p className={styles.error}>Не удалось загрузить очередь модерации.</p>
          <Button type="button" variant="secondary" size="sm" onClick={review.reload}>Повторить</Button>
        </div>
      )}
      {!firstLoad && !review.error && review.items.length === 0 && (
        <p className={styles.state}>Материалов на проверке нет.</p>
      )}

      {review.items.length > 0 && (
        <ul className={styles.list} aria-label="Материалы на проверке">
          {review.items.map(item => {
            const error = review.actionError?.uuid === item.uuid ? review.actionError.message
              : previewError?.uuid === item.uuid ? previewError.message : null;
            const errorId = `review-error-${item.uuid}`;
            return (
              <li key={item.uuid} className={styles.item}>
                <div className={styles.head}>
                  <span className={styles.title}>{item.title}</span>
                  <span className={styles.meta}>
                    {item.created_by_name || 'Автор не указан'} · создан {formatMaterialDate(item.created_at)}
                  </span>
                </div>
                {item.excerpt && <p className={styles.excerpt}>{item.excerpt}</p>}
                <div className={styles.actions}>
                  <Button type="button" variant="ghost" size="sm" onClick={() => openPreview(item)}
                    loading={loadingPreview === item.uuid}>
                    Просмотреть
                  </Button>
                  <Button type="button" variant="secondary" size="sm" onClick={() => setReturning(item)}
                    aria-describedby={error ? errorId : undefined}>
                    Вернуть на доработку
                  </Button>
                  <Button type="button" size="sm" onClick={() => setConfirmPublish(item)}
                    loading={review.pendingUuid === item.uuid}
                    aria-describedby={error ? errorId : undefined}>
                    Опубликовать
                  </Button>
                </div>
                {error && <p id={errorId} className={styles.error} role="alert">{error}</p>}
              </li>
            );
          })}
        </ul>
      )}

      {review.hasMore && !review.error && (
        <div className={styles.more}>
          <Button type="button" variant="secondary" onClick={review.loadMore} loading={review.loading}>
            Показать ещё
          </Button>
        </div>
      )}

      {preview && (
        <ContentPreview
          open
          onClose={() => setPreview(null)}
          title={preview.title}
          excerpt={preview.excerpt}
          content={preview.content}
          coverUrl={preview.cover_image_url}
          tags={(preview.tags || []).map(t => t.name)}
          categories={(preview.categories || []).map(c => c.name)}
          authorName={preview.created_by_name}
        />
      )}

      <ConfirmDialog
        open={confirmPublish !== null}
        title="Опубликовать материал?"
        description={confirmPublish
          ? `«${confirmPublish.title}» появится в библиотеке на сайте и в кабинетах.`
          : ''}
        confirmLabel="Опубликовать"
        loading={confirmPublish !== null && review.pendingUuid === confirmPublish.uuid}
        onConfirm={doPublish}
        onClose={() => setConfirmPublish(null)}
      />

      {returning && (
        <ReturnDialog
          article={returning}
          loading={review.pendingUuid === returning.uuid}
          onConfirm={doReturn}
          onClose={() => setReturning(null)}
        />
      )}
    </div>
  );
}
