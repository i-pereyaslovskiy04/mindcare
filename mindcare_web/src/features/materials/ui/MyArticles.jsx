import { useState } from 'react';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import FilterChip from '../../../components/UI/FilterChip/FilterChip';
import ArticleFormModal from '../../admin/articles/components/ArticleFormModal';
import ConfirmDialog from '../../assignments/ui/ConfirmDialog';
import useMyArticles from '../hooks/useMyArticles';
import {
  ARTICLE_STATUS_LABELS, ARTICLE_STATUS_TONES, articleStatus,
} from '../lib/articleStatus';
import { formatMaterialDate } from '../lib/normalizeArticle';
import styles from './MyArticles.module.css';

const ALL_FILTERS = [
  { value: '', label: 'Все' },
  { value: 'draft', label: ARTICLE_STATUS_LABELS.draft },
  { value: 'in_review', label: ARTICLE_STATUS_LABELS.in_review },
  { value: 'needs_changes', label: ARTICLE_STATUS_LABELS.needs_changes },
  { value: 'published', label: ARTICLE_STATUS_LABELS.published },
];
// Супервизор публикует сам — «На проверке» у него не бывает.
const SUPERVISOR_FILTERS = ALL_FILTERS.filter(f => f.value !== 'in_review');
const EDITABLE = ['draft', 'needs_changes', 'published'];
const SUBMITTABLE = ['draft', 'needs_changes'];
const DELETABLE = ['draft', 'needs_changes'];

/**
 * «Мои материалы» автора (ADR-034): свои статьи со статусом модерации,
 * создание и правка (черновик), удаление черновика. Психолог отправляет
 * материал на проверку — публикует проверяющий; супервизор (role="supervisor",
 * Дополнение 2026-10-28) публикует свой материал сам, с подтверждением.
 * Правка опубликованной снимает её с публикации — перед этим показывается
 * предупреждение.
 */
export default function MyArticles({ role = 'psychologist' }) {
  const selfPublish = role === 'supervisor';
  const filters = selfPublish ? SUPERVISOR_FILTERS : ALL_FILTERS;
  const list = useMyArticles({ role });
  const [form, setForm] = useState(null);           // null | { article: null | full }
  const [loadingEdit, setLoadingEdit] = useState(null);
  const [editError, setEditError] = useState(null);
  const [warnEdit, setWarnEdit] = useState(null);   // опубликованная статья
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [confirmPublish, setConfirmPublish] = useState(null);

  async function openEdit(item) {
    setEditError(null);
    setLoadingEdit(item.uuid);
    try {
      const full = await list.loadForEdit(item.uuid);
      setForm({ article: full });
    } catch {
      setEditError({ uuid: item.uuid, message: 'Не удалось открыть материал. Повторите попытку.' });
    } finally {
      setLoadingEdit(null);
    }
  }

  function handleEdit(item) {
    if (articleStatus(item) === 'published') setWarnEdit(item);
    else openEdit(item);
  }

  async function confirmRemove() {
    if (!confirmDelete) return;
    await list.remove(confirmDelete.uuid);
    setConfirmDelete(null);
  }

  async function doPublish() {
    if (!confirmPublish) return;
    await list.publish(confirmPublish.uuid);
    setConfirmPublish(null);
  }

  const firstLoad = list.loading && list.items.length === 0;

  return (
    <div className={styles.wrap}>
      <div className={styles.toolbar}>
        <div className={styles.filters} role="group" aria-label="Статус материалов">
          {filters.map(f => (
            <FilterChip key={f.value || 'all'} active={list.status === f.value} onClick={() => list.setStatus(f.value)}>
              {f.label}
            </FilterChip>
          ))}
        </div>
        <Button type="button" onClick={() => setForm({ article: null })}>Новый материал</Button>
      </div>

      {firstLoad && <p className={styles.state} role="status">Загружаем материалы…</p>}

      {list.error && (
        <div className={styles.errorBox} role="alert">
          <p className={styles.error}>Не удалось загрузить материалы.</p>
          <Button type="button" variant="secondary" size="sm" onClick={list.reload}>Повторить</Button>
        </div>
      )}

      {!firstLoad && !list.error && list.items.length === 0 && (
        <p className={styles.state}>
          {list.status ? 'Материалов с таким статусом нет.' : 'Вы ещё не создали ни одного материала.'}
        </p>
      )}

      {list.items.length > 0 && (
        <ul className={styles.list} aria-label="Мои материалы">
          {list.items.map(item => {
            const st = articleStatus(item);
            const error = list.actionError?.uuid === item.uuid ? list.actionError.message
              : editError?.uuid === item.uuid ? editError.message : null;
            const errorId = `my-article-error-${item.uuid}`;
            return (
              <li key={item.uuid} className={styles.item}>
                <div className={styles.head}>
                  <span className={styles.title}>{item.title}</span>
                  <Badge tone={ARTICLE_STATUS_TONES[st]}>{ARTICLE_STATUS_LABELS[st]}</Badge>
                </div>
                {item.excerpt && <p className={styles.excerpt}>{item.excerpt}</p>}
                {st === 'needs_changes' && item.review_comment && (
                  <p className={styles.comment}>
                    <b>Комментарий проверяющего:</b> {item.review_comment}
                  </p>
                )}
                {st === 'in_review' && (
                  <p className={styles.meta}>Материал на проверке — до решения его нельзя изменить.</p>
                )}
                <div className={styles.foot}>
                  <span className={styles.meta}>
                    Создан {formatMaterialDate(item.created_at)}
                    {item.published_at && st === 'published' && ` · опубликован ${formatMaterialDate(item.published_at)}`}
                  </span>
                  <div className={styles.actions}>
                    {EDITABLE.includes(st) && (
                      <Button type="button" variant="ghost" size="sm" onClick={() => handleEdit(item)}
                        loading={loadingEdit === item.uuid} aria-describedby={error ? errorId : undefined}>
                        Редактировать
                      </Button>
                    )}
                    {SUBMITTABLE.includes(st) && (selfPublish ? (
                      <Button type="button" size="sm"
                        onClick={() => setConfirmPublish(item)}
                        aria-describedby={error ? errorId : undefined}>
                        Опубликовать
                      </Button>
                    ) : (
                      <Button type="button" variant="secondary" size="sm"
                        onClick={() => list.submit(item.uuid)}
                        loading={list.pendingUuid === item.uuid}
                        aria-describedby={error ? errorId : undefined}>
                        Отправить на проверку
                      </Button>
                    ))}
                    {DELETABLE.includes(st) && (
                      <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmDelete(item)}>
                        Удалить
                      </Button>
                    )}
                  </div>
                </div>
                {error && <p id={errorId} className={styles.error} role="alert">{error}</p>}
              </li>
            );
          })}
        </ul>
      )}

      {list.hasMore && !list.error && (
        <div className={styles.more}>
          <Button type="button" variant="secondary" onClick={list.loadMore} loading={list.loading}>
            Показать ещё
          </Button>
        </div>
      )}

      {form && (
        <ArticleFormModal
          open
          mode="author"
          authorRole={role}
          article={form.article}
          onClose={() => setForm(null)}
          onSaved={() => { setForm(null); list.reload(); }}
        />
      )}

      <ConfirmDialog
        open={warnEdit !== null}
        title="Редактировать опубликованный материал?"
        description={warnEdit
          ? `«${warnEdit.title}» сейчас опубликован. После сохранения он снимется с публикации и перейдёт в черновик — ${selfPublish ? 'после правки опубликуйте его снова' : 'потребуется повторно отправить его на проверку'}.`
          : ''}
        confirmLabel="Редактировать"
        onConfirm={() => { const item = warnEdit; setWarnEdit(null); openEdit(item); }}
        onClose={() => setWarnEdit(null)}
      />

      <ConfirmDialog
        open={confirmPublish !== null}
        title="Опубликовать материал?"
        description={confirmPublish
          ? `«${confirmPublish.title}» появится в библиотеке на сайте и в кабинетах.`
          : ''}
        confirmLabel="Опубликовать"
        loading={confirmPublish !== null && list.pendingUuid === confirmPublish.uuid}
        onConfirm={doPublish}
        onClose={() => setConfirmPublish(null)}
      />

      <ConfirmDialog
        open={confirmDelete !== null}
        title="Удалить материал?"
        description={confirmDelete ? `«${confirmDelete.title}» будет удалён без возможности восстановления.` : ''}
        confirmLabel="Удалить"
        confirmTone="danger"
        loading={confirmDelete !== null && list.pendingUuid === confirmDelete.uuid}
        onConfirm={confirmRemove}
        onClose={() => setConfirmDelete(null)}
      />
    </div>
  );
}
