import { useAdminUsers } from '../../../features/admin-users/hooks/useAdminUsers';
import UsersFilters from '../../../features/admin-users/ui/UsersFilters';
import UsersTable from '../../../features/admin-users/ui/UsersTable';
import styles from './UsersPage.module.css';

const PAGE_SIZE = 20;

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
      <span className={styles.pageInfo}>
        Стр. {page} из {totalPages}
      </span>
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
    page, setPage,
    query, setQuery,
    filters, setFilters,
  } = useAdminUsers();

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Пользователи</h1>
        {!loading && (
          <span className={styles.total}>{total} всего</span>
        )}
      </div>

      <UsersFilters
        query={query}
        onQueryChange={setQuery}
        filters={filters}
        onFiltersChange={setFilters}
      />

      <UsersTable items={items} loading={loading} error={error} />

      <Pagination
        page={page}
        total={total}
        size={PAGE_SIZE}
        onPageChange={setPage}
      />
    </div>
  );
}
