import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAdminTests } from '../hooks/useAdminTests';
import TestsTable from '../components/TestsTable';
import TestPreviewModal from '../components/TestPreviewModal';
import { fromBackendQuestion } from '../lib/testShape';
import { deleteTest, getAdminTest } from '../../../../api/tests.api';
import Select from '../../../../components/UI/Select/Select';
import Button from '../../../../components/UI/Button/Button';
import styles from './AdminTestsPage.module.css';

/**
 * Полный тест из admin API → форма-представление, которое принимает
 * TestPreviewModal (тот же shape, что строит TestFormPage при загрузке). Ключи
 * _key синтезируются локальным счётчиком — модалке нужны стабильные id.
 */
function toPreviewShape(test) {
  let keySeq = 0;
  const nextKey = () => `pk${++keySeq}`;
  const questions = (test.questions || [])
    .slice()
    .sort((a, b) => a.question_order - b.question_order)
    .map((q) => fromBackendQuestion(q, nextKey));
  const interpretations = (test.interpretations || []).map((it) => ({
    _key: nextKey(),
    scale_name: it.scale_name || '',
    min_score: it.min_score,
    max_score: it.max_score,
    label: it.label || '',
    recommendation: it.recommendation || '',
  }));
  return {
    title: test.title || '',
    description: test.description || '',
    scoring: test.scoring || 'sum',
    questions,
    interpretations,
  };
}

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

  const [preview, setPreview]           = useState(null);   // shaped test
  const [previewLoadingUuid, setPreviewLoadingUuid] = useState(null);
  const [previewError, setPreviewError] = useState('');

  const pageCount = Math.ceil(total / 20);

  async function handlePreview(item) {
    if (previewLoadingUuid) return;
    setPreviewLoadingUuid(item.uuid);
    setPreviewError('');
    try {
      const full = await getAdminTest(item.uuid);
      setPreview(toPreviewShape(full));
    } catch (err) {
      setPreviewError(err.message || 'Не удалось загрузить тест для предпросмотра');
    } finally {
      setPreviewLoadingUuid(null);
    }
  }

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

      {previewError && (
        <p className={styles.previewError} role="alert">{previewError}</p>
      )}

      <TestsTable
        items={items}
        loading={loading}
        error={error}
        onPreview={handlePreview}
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

      {preview && (
        <TestPreviewModal
          title={preview.title}
          description={preview.description}
          scoring={preview.scoring}
          questions={preview.questions}
          interpretations={preview.interpretations}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}
