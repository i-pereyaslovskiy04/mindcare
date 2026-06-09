import { useState } from 'react';
import { useAdminCategories } from '../hooks/useAdminCategories';
import CategoriesTable from '../components/CategoriesTable';
import CategoryFormModal from '../components/CategoryFormModal';
import { deleteCategory } from '../../../../api/categories.api';
import Select from '../../../../components/UI/Select/Select';
import Button from '../../../../components/UI/Button/Button';
import styles from './CategoriesPage.module.css';

const STATUS_OPTIONS = [
  { value: '',      label: 'Все типы' },
  { value: 'true',  label: 'Активные' },
  { value: 'false', label: 'Скрытые' },
];

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
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          + Добавить тип
        </Button>
      </div>

      <div className={styles.toolbar}>
        <input
          className={styles.search}
          placeholder="Поиск по названию..."
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        <Select
          style={{ minWidth: 150 }}
          value={filters.is_active === null ? '' : String(filters.is_active)}
          options={STATUS_OPTIONS}
          onChange={val => setFilters({ is_active: val === '' ? null : val === 'true' })}
          placeholder="Все типы"
        />
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
              <Button variant="secondary" onClick={() => setDeleteTarget(null)} disabled={deleting}>
                Отмена
              </Button>
              <Button variant="danger" onClick={handleDeleteConfirm} disabled={deleting}>
                {deleting ? 'Скрытие…' : 'Скрыть'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
