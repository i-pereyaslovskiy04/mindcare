import { useState } from 'react';
import { useAdminTags } from '../hooks/useAdminTags';
import { deleteTag } from '../../../../api/tags.api';
import TagsTable from '../components/TagsTable';
import TagFormModal from '../components/TagFormModal';
import styles from './TagsPage.module.css';

function pluralTag(n) {
  if (n % 10 === 1 && n % 100 !== 11) return 'тема';
  if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20)) return 'темы';
  return 'тем';
}

function pluralMaterial(n) {
  if (n % 10 === 1 && n % 100 !== 11) return 'материале';
  if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20)) return 'материалах';
  return 'материалах';
}

export default function TagsPage() {
  const { items, loading, error, total, query, setQuery, refetch } = useAdminTags();

  const [createOpen, setCreateOpen]     = useState(false);
  const [editTarget, setEditTarget]     = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteUsages, setDeleteUsages] = useState(0);
  const [deleting, setDeleting]         = useState(false);
  const [deleteError, setDeleteError]   = useState('');

  function handleEdit(tag) {
    setEditTarget(tag);
  }

  function handleDelete(tag, totalUsages) {
    setDeleteTarget(tag);
    setDeleteUsages(totalUsages);
    setDeleteError('');
  }

  function closeDelete() {
    if (deleting) return;
    setDeleteTarget(null);
    setDeleteError('');
  }

  async function confirmDelete() {
    if (deleting) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteTag(deleteTarget.uuid);
      setDeleteTarget(null);
      refetch();
    } catch (err) {
      setDeleteError(err.message || 'Не удалось удалить тему');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Темы</h1>
          <p className={styles.subtitle}>
            {total} {pluralTag(total)}
          </p>
        </div>
        <button className={styles.btnCreate} onClick={() => setCreateOpen(true)}>
          + Новая тема
        </button>
      </div>

      <div className={styles.toolbar}>
        <input
          type="text"
          className={styles.search}
          placeholder="Поиск по названию..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <TagsTable
        items={items}
        loading={loading}
        error={error}
        onEdit={handleEdit}
        onDelete={handleDelete}
      />

      {createOpen && (
        <TagFormModal
          mode="create"
          onSuccess={() => { setCreateOpen(false); refetch(); }}
          onClose={() => setCreateOpen(false)}
        />
      )}

      {editTarget && (
        <TagFormModal
          mode="edit"
          tag={editTarget}
          onSuccess={() => { setEditTarget(null); refetch(); }}
          onClose={() => setEditTarget(null)}
        />
      )}

      {deleteTarget && (
        <div className={styles.overlay} onClick={closeDelete}>
          <div className={styles.dialog} onClick={(e) => e.stopPropagation()}>
            <h3 className={styles.dialogTitle}>
              Удалить тему «{deleteTarget.name}»?
            </h3>
            {deleteUsages > 0 && (
              <p className={styles.dialogWarning}>
                Тема используется в {deleteUsages} {pluralMaterial(deleteUsages)}.
                Все связи будут удалены автоматически.
              </p>
            )}
            {deleteError && (
              <p className={styles.dialogError}>{deleteError}</p>
            )}
            <div className={styles.dialogActions}>
              <button
                className={styles.btnSecondary}
                onClick={closeDelete}
                disabled={deleting}
              >
                Отмена
              </button>
              <button
                className={styles.btnDanger}
                onClick={confirmDelete}
                disabled={deleting}
              >
                {deleting ? 'Удаление...' : 'Удалить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
