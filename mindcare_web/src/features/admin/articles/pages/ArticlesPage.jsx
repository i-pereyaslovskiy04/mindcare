import { useState } from 'react';
import { useAdminArticles } from '../hooks/useAdminArticles';
import ArticlesTable from '../components/ArticlesTable';
import ArticleFormModal from '../components/ArticleFormModal';
import { deleteArticle } from '../../../../api/articles.api';
import styles from './ArticlesPage.module.css';

export default function ArticlesPage() {
  const { items, loading, error, total, page, setPage, query, setQuery, filters, setFilters, refetch } =
    useAdminArticles();

  const [createOpen, setCreateOpen]   = useState(false);
  const [editTarget, setEditTarget]   = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting]       = useState(false);
  const [deleteError, setDeleteError] = useState('');

  const pageCount = Math.ceil(total / 20);

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
        <select
          className={styles.select}
          value={filters.is_published === null ? '' : String(filters.is_published)}
          onChange={e => {
            const v = e.target.value;
            setFilters({ is_published: v === '' ? null : v === 'true' });
          }}
        >
          <option value="">Все статусы</option>
          <option value="true">Опубликованные</option>
          <option value="false">Черновики</option>
        </select>
      </div>

      {loading && <p className={styles.status}>Загрузка…</p>}
      {error   && <p className={styles.error}>{error}</p>}

      {!loading && (
        <ArticlesTable
          items={items}
          onEdit={item => setEditTarget(item)}
          onDelete={item => { setDeleteTarget(item); setDeleteError(''); }}
        />
      )}

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
