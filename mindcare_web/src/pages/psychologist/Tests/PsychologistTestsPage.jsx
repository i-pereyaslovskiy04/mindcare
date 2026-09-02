import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMyTests } from '../../../features/psychologist/hooks/useMyTests';
import TestsTable from '../../../features/admin/tests/components/TestsTable';
import TestPreviewModal from '../../../features/admin/tests/components/TestPreviewModal';
import { fromBackendQuestion } from '../../../features/admin/tests/lib/testShape';
import {
  deleteMyTest, getMyTest, submitTestForReview, previewMyScore,
} from '../../../api/tests.api';
import Select from '../../../components/UI/Select/Select';
import Button from '../../../components/UI/Button/Button';
import styles from './PsychologistTestsPage.module.css';

/** Тот же shape, что строит TestFormPage при загрузке — TestPreviewModal его и ждёт. */
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
  { value: '',              label: 'Все статусы' },
  { value: 'draft',         label: 'Черновик' },
  { value: 'in_review',     label: 'На проверке' },
  { value: 'published',     label: 'Опубликован' },
  { value: 'needs_changes', label: 'Нужны правки' },
];

// Редактировать/удалить можно только пока тест draft/needs_changes — на
// проверке или опубликован решение уже не за автором (ADR-016).
const EDITABLE_STATUSES = ['draft', 'needs_changes'];

export default function PsychologistTestsPage() {
  const navigate = useNavigate();
  const { items, loading, error, total, page, setPage, query, setQuery, filters, setFilters, refetch } =
    useMyTests();

  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting]         = useState(false);
  const [deleteError, setDeleteError]   = useState('');

  const [preview, setPreview]           = useState(null);
  const [previewLoadingUuid, setPreviewLoadingUuid] = useState(null);
  const [previewError, setPreviewError] = useState('');

  const [actionError, setActionError]   = useState('');
  const [submittingUuid, setSubmittingUuid] = useState(null);

  const pageCount = Math.ceil(total / 20);

  async function handlePreview(item) {
    if (previewLoadingUuid) return;
    setPreviewLoadingUuid(item.uuid);
    setPreviewError('');
    try {
      const full = await getMyTest(item.uuid);
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
      await deleteMyTest(deleteTarget.uuid);
      setDeleteTarget(null);
      refetch();
    } catch (err) {
      setDeleteError(err.message);
    } finally {
      setDeleting(false);
    }
  }

  async function handleSubmitForReview(item) {
    if (submittingUuid) return;
    setActionError('');
    setSubmittingUuid(item.uuid);
    try {
      await submitTestForReview(item.uuid);
      refetch();
    } catch (err) {
      setActionError(err.message || 'Не удалось отправить тест на модерацию');
    } finally {
      setSubmittingUuid(null);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Мои тесты</h1>
        <Button variant="primary" onClick={() => navigate('/psychologist/tests/new')}>
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
          style={{ minWidth: 150 }}
          value={filters.status ?? ''}
          options={STATUS_OPTIONS}
          onChange={(val) => setFilters({ status: val || null })}
          placeholder="Все статусы"
        />
      </div>

      {previewError && <p className={styles.actionError} role="alert">{previewError}</p>}
      {actionError && <p className={styles.actionError} role="alert">{actionError}</p>}

      <TestsTable
        items={items}
        loading={loading}
        error={error}
        onPreview={handlePreview}
        onEdit={(item) => navigate(`/psychologist/tests/${item.uuid}`)}
        onDelete={(item) => { setDeleteTarget(item); setDeleteError(''); }}
        onSubmitForReview={handleSubmitForReview}
        restrictEditToStatuses={EDITABLE_STATUSES}
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
              Черновик «{deleteTarget.title}» будет удалён без возможности восстановления.
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
          previewFn={previewMyScore}
        />
      )}
    </div>
  );
}
