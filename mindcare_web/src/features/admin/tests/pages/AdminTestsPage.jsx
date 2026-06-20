import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAdminTests } from '../hooks/useAdminTests';
import TestsTable from '../components/TestsTable';
import { deleteTest } from '../../../../api/tests.api';
import Select from '../../../../components/UI/Select/Select';
import Button from '../../../../components/UI/Button/Button';
import styles from './AdminTestsPage.module.css';

const STATUS_OPTIONS = [
  { value: '',      label: 'Все статусы' },
  { value: 'true',  label: 'Активные' },
  { value: 'false', label: 'Скрытые' },
];

export default function AdminTestsPage() {
  const navigate = useNavigate();
  const { items, loading, error, total, page, setPage, query, setQuery, filters, setFilters, refetch } =
    useAdminTests();

  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting]         = useState(false);
  const [deleteError, setDeleteError]   = useState('');

  const pageCount = Math.ceil(total / 20);

  async function handleDeleteConfirm() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteTest(deleteTarget.uuid);
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
        <h1 className={styles.title}>Тесты</h1>
        <Button variant="primary" onClick={() => navigate('/admin/tests/new')}>
          + Создать тест
        </Button>
      </div>

      <div className={styles.toolbar}>
        <input
          className={styles.search}
          placeholder="Поиск по названию..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Select
          style={{ minWidth: 160 }}
          value={filters.is_active === null ? '' : String(filters.is_active)}
          options={STATUS_OPTIONS}
          onChange={(val) => setFilters({ is_active: val === '' ? null : val === 'true' })}
          placeholder="Все статусы"
        />
      </div>

      <TestsTable
        items={items}
        loading={loading}
        error={error}
        onEdit={(item) => navigate(`/admin/tests/${item.uuid}`)}
        onDelete={(item) => { setDeleteTarget(item); setDeleteError(''); }}
      />

      {pageCount > 1 && (
        <div className={styles.pagination}>
          <Button type="button" variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>‹</Button>
          <span>{page} / {pageCount}</span>
          <Button type="button" variant="secondary" size="sm" disabled={page >= pageCount} onClick={() => setPage((p) => p + 1)}>›</Button>
        </div>
      )}

      {deleteTarget && (
        <div className={styles.overlay} onClick={() => !deleting && setDeleteTarget(null)}>
          <div className={styles.dialog} onClick={(e) => e.stopPropagation()}>
            <h3 className={styles.dialogTitle}>Удалить тест?</h3>
            <p className={styles.dialogBody}>
              «{deleteTarget.title}» будет скрыт и удалён из каталога. Уже полученные
              результаты студентов сохранятся.
            </p>
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
