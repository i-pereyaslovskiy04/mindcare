import { useState } from 'react';
import { useAdminCategories } from '../hooks/useAdminCategories';
import CategoriesTable from '../components/CategoriesTable';
import CategoryFormModal from '../components/CategoryFormModal';
import { deleteCategory } from '../../../../api/categories.api';
import styles from './CategoriesPage.module.css';

export default function CategoriesPage() {
  const {
    items, loading, error, total,
    page, setPage, size,
    query, setQuery,
    filters, setFilters,
    refetch,
  } = useAdminCategories();

  const [createOpen, setCreateOpen]       = useState(false);
  const [editTarget, setEditTarget]       = useState(null);
  const [editLoadingId, setEditLoadingId] = useState(null);
  const [deleteTarget, setDeleteTarget]   = useState(null);
  const [deleting, setDeleting]           = useState(false);
  const [deleteError, setDeleteError]     = useState('');

  const pageCount = Math.ceil(total / size);

  // При клике на «Редактировать» открываем форму с данными строки из таблицы.
  // Отдельный GET не нужен — CategoryRead уже содержит все поля формы.
  function handleEdit(item) {
    setEditLoadingId(item.id);
    setEditTarget(item);
    setEditLoadingId(null);
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteCategory(deleteTarget.id);
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
        <h1 className={styles.title}>Типы материалов</h1>
        <button className={styles.btnCreate} onClick={() => setCreateOpen(true)}>
          + Добавить тип
        </button>
      </div>

      <div className={styles.toolbar}>
        <input
          className={styles.search}
          placeholder="Поиск по названию..."
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        <select
          className={styles.select}
          value={filters.is_active === null ? '' : String(filters.is_active)}
          onChange={e => {
            const v = e.target.value;
            setFilters({ is_active: v === '' ? null : v === 'true' });
          }}
        >
          <option value="">Все типы</option>
          <option value="true">Активные</option>
          <option value="false">Скрытые</option>
        </select>
      </div>

      <CategoriesTable
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
        <CategoryFormModal
          open
          onClose={() => setCreateOpen(false)}
          onSaved={() => { setCreateOpen(false); refetch(); }}
        />
      )}

      {editTarget && (
        <CategoryFormModal
          open
          category={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={() => { setEditTarget(null); refetch(); }}
        />
      )}

      {deleteTarget && (
        <div className={styles.overlay} onClick={() => !deleting && setDeleteTarget(null)}>
          <div className={styles.dialog} onClick={e => e.stopPropagation()}>
            <h3 className={styles.dialogTitle}>Скрыть тип материалов?</h3>
            <p className={styles.dialogBody}>
              «{deleteTarget.name}» будет деактивирован и перестанет
              предлагаться при добавлении материалов. Существующие
              привязки материалов сохранятся.
            </p>
            {deleteError && (
              <p className={styles.dialogError}>{deleteError}</p>
            )}
            <div className={styles.dialogActions}>
              <button
                className={styles.btnCancel}
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
              >
                Отмена
              </button>
              <button
                className={styles.btnDanger}
                onClick={handleDeleteConfirm}
                disabled={deleting}
              >
                {deleting ? 'Скрытие…' : 'Скрыть'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
