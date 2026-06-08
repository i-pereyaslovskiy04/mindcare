import { useState } from 'react';
import { useAdminArticles } from '../hooks/useAdminArticles';
import ArticlesTable from '../components/ArticlesTable';
import ArticleFormModal from '../components/ArticleFormModal';
import { deleteArticle, getAdminArticleItem } from '../../../../api/articles.api';
import Select from '../../../../components/UI/Select/Select';
import styles from './ArticlesPage.module.css';

const STATUS_OPTIONS = [
  { value: '',      label: 'Все статусы' },
  { value: 'true',  label: 'Опубликованные' },
  { value: 'false', label: 'Черновики' },
];

export default function ArticlesPage() {
  const { items, loading, error, total, page, setPage, query, setQuery, filters, setFilters, refetch } =
    useAdminArticles();

  const [createOpen, setCreateOpen]     = useState(false);
  const [editTarget, setEditTarget]     = useState(null);
  const [editLoadingId, setEditLoadingId] = useState(null);
  const [editError, setEditError]         = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting]         = useState(false);
  const [deleteError, setDeleteError]   = useState('');

  const pageCount = Math.ceil(total / 20);

  async function handleEdit(item) {
    setEditLoadingId(item.uuid);
    setEditError('');
    try {
      const full = await getAdminArticleItem(item.uuid);
      setEditTarget(full);
    } catch (err) {
      setEditError(`Не удалось загрузить материал: ${err.message}`);
    } finally {
      setEditLoadingId(null);
    }
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteArticle(deleteTarget.uuid);
      setDeleteTarget(null);
      refetch();
    } catch (err) {
      setDeleteError(err.message);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Материалы</h1>
        <button className={styles.btnCreate} onClick={() => setCreateOpen(true)}>
          + Добавить
        </button>
      </div>

      <div className={styles.toolbar}>
        <input
          className={styles.search}
          placeholder="Поиск по заголовку..."
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        <Select
          style={{ minWidth: 160 }}
          value={filters.is_published === null ? '' : String(filters.is_published)}
          options={STATUS_OPTIONS}
          onChange={val => setFilters({ is_published: val === '' ? null : val === 'true' })}
          placeholder="Все статусы"
        />
      </div>

      {editError && <p className={styles.error}>{editError}</p>}

      <ArticlesTable
        items={items}
        loading={loading}
        error={error}
        onEdit={handleEdit}
        onDelete={item => { setDeleteTarget(item); setDeleteError(''); }}
        editLoadingId={editLoadingId}
      />

      {pageCount > 1 && (
        <div className={styles.pagination}>
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>‹</button>
          <span>{page} / {pageCount}</span>
          <button disabled={page >= pageCount} onClick={() => setPage(p => p + 1)}>›</button>
        </div>
      )}

      {createOpen && (
        <ArticleFormModal
          open
          onClose={() => setCreateOpen(false)}
          onSaved={() => { setCreateOpen(false); refetch(); }}
        />
      )}

      {editTarget && (
        <ArticleFormModal
          open
          article={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={() => { setEditTarget(null); refetch(); }}
        />
      )}

      {deleteTarget && (
        <div className={styles.overlay} onClick={() => !deleting && setDeleteTarget(null)}>
          <div className={styles.dialog} onClick={e => e.stopPropagation()}>
            <h3 className={styles.dialogTitle}>Удалить материал?</h3>
            <p className={styles.dialogBody}>«{deleteTarget.title}» будет удалён. Действие необратимо.</p>
            {deleteError && <p className={styles.dialogError}>{deleteError}</p>}
            <div className={styles.dialogActions}>
              <button className={styles.btnCancel} onClick={() => setDeleteTarget(null)} disabled={deleting}>
                Отмена
              </button>
              <button className={styles.btnDanger} onClick={handleDeleteConfirm} disabled={deleting}>
                {deleting ? 'Удаление…' : 'Удалить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
