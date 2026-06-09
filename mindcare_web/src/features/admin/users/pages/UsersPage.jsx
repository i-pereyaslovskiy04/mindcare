import { useState } from 'react';
import { useAdminUsers } from '../hooks/useAdminUsers';
import UsersFilters from '../components/UsersFilters';
import UsersTable from '../components/UsersTable';
import UserCreateModal from '../components/UserCreateModal';
import UserEditModal from '../components/UserEditModal';
import DeleteConfirmDialog from '../components/DeleteConfirmDialog';
import Button from '../../../../components/UI/Button/Button';
import styles from './UsersPage.module.css';

function Pagination({ page, total, size, onPageChange }) {
  const totalPages = Math.max(1, Math.ceil(total / size));
  if (totalPages <= 1) return null;

  return (
    <div className={styles.pagination}>
      <button
        className={styles.pageBtn}
        disabled={page === 1}
        onClick={() => onPageChange(page - 1)}
      >
        ← Назад
      </button>
      <span className={styles.pageInfo}>Стр. {page} из {totalPages}</span>
      <button
        className={styles.pageBtn}
        disabled={page === totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        Вперёд →
      </button>
    </div>
  );
}

export default function UsersPage() {
  const {
    items, loading, error, total,
    page, setPage, size,
    query, setQuery,
    filters, setFilters,
    refetch,
  } = useAdminUsers();

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null);   // user object for edit
  const [deleteTarget, setDeleteTarget] = useState(null); // user object for delete

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={styles.title}>Пользователи</h1>
          {!loading && <span className={styles.total}>{total} всего</span>}
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          + Добавить
        </Button>
      </div>

      <UsersFilters
        query={query}
        onQueryChange={setQuery}
        filters={filters}
        onFiltersChange={setFilters}
      />

      <UsersTable
        items={items}
        loading={loading}
        error={error}
        onEdit={(user) => setEditTarget(user)}
        onDelete={(user) => setDeleteTarget(user)}
      />

      <Pagination
        page={page}
        total={total}
        size={size}
        onPageChange={setPage}
      />

      {/* ── Modals ── */}
      <UserCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => { setCreateOpen(false); refetch(); }}
      />

      <UserEditModal
        open={!!editTarget}
        uuid={editTarget?.uuid}
        userInfo={editTarget}
        onClose={() => setEditTarget(null)}
        onUpdated={() => { setEditTarget(null); refetch(); }}
      />

      <DeleteConfirmDialog
        open={!!deleteTarget}
        userInfo={deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onDeleted={() => { setDeleteTarget(null); refetch(); }}
      />
    </div>
  );
}
