import { useState } from 'react';
import { useAdminNews } from '../hooks/useAdminNews';
import NewsTable from '../components/NewsTable';
import NewsFormModal from '../components/NewsFormModal';
import { deleteNews, getAdminNewsItem } from '../../../../api/news.api';
import Select from '../../../../components/UI/Select/Select';
import Button from '../../../../components/UI/Button/Button';
import styles from './NewsPage.module.css';

const STATUS_OPTIONS = [
  { value: '',      label: 'Все статусы' },
  { value: 'true',  label: 'Опубликованные' },
  { value: 'false', label: 'Черновики' },
];

export default function NewsPage() {
  const { items, loading, error, total, page, setPage, query, setQuery, filters, setFilters, refetch } =
    useAdminNews();

  const [createOpen, setCreateOpen]     = useState(false);
  const [editTarget, setEditTarget]     = useState(null);
  // editLoading — пока грузим полный объект новости для редактирования
  const [editLoadingId, setEditLoadingId] = useState(null); // uuid строки которая грузится
  const [editError, setEditError]         = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting]         = useState(false);
  const [deleteError, setDeleteError]   = useState('');

  const pageCount = Math.ceil(total / 20);

  // При клике «Редактировать» запрашиваем полный объект новости (с content).
  // Таблица хранит только NewsListItem — без поля content,
  // поэтому нужен отдельный GET /api/admin/news/{uuid}.
  async function handleEdit(item) {
    setEditLoadingId(item.uuid);
    setEditError('');
    try {
      const full = await getAdminNewsItem(item.uuid);
      setEditTarget(full);
    } catch (err) {
      setEditError(`Не удалось загрузить новость: ${err.message}`);
    } finally {
      setEditLoadingId(null);
    }
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteNews(deleteTarget.uuid);
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
        <h1 className={styles.title}>Новости</h1>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          + Добавить
        </Button>
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

      <NewsTable
        items={items}
        loading={loading}
        error={error}
        onEdit={handleEdit}
        onDelete={item => { setDeleteTarget(item); setDeleteError(''); }}
        editLoadingId={editLoadingId}
      />

      {pageCount > 1 && (
        <div className={styles.pagination}>
          <Button type="button" variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>‹</Button>
          <span>{page} / {pageCount}</span>
          <Button type="button" variant="secondary" size="sm" disabled={page >= pageCount} onClick={() => setPage(p => p + 1)}>›</Button>
        </div>
      )}

      {createOpen && (
        <NewsFormModal
          open
          onClose={() => setCreateOpen(false)}
          onSaved={() => { setCreateOpen(false); refetch(); }}
        />
      )}

      {editTarget && (
        <NewsFormModal
          open
          news={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={() => { setEditTarget(null); refetch(); }}
        />
      )}

      {deleteTarget && (
        <div className={styles.overlay} onClick={() => !deleting && setDeleteTarget(null)}>
          <div className={styles.dialog} onClick={e => e.stopPropagation()}>
            <h3 className={styles.dialogTitle}>Удалить новость?</h3>
            <p className={styles.dialogBody}>«{deleteTarget.title}» будет удалена. Действие необратимо.</p>
            {deleteError && <p className={styles.dialogError}>{deleteError}</p>}
            <div className={styles.dialogActions}>
              <Button variant="secondary" onClick={() => setDeleteTarget(null)} disabled={deleting}>
                Отмена
              </Button>
              <Button variant="danger" onClick={handleDeleteConfirm} disabled={deleting}>
                {deleting ? 'Удаление…' : 'Удалить'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
