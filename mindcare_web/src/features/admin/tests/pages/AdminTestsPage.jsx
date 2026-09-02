import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAdminTests } from '../hooks/useAdminTests';
import TestsTable from '../components/TestsTable';
import TestPreviewModal from '../components/TestPreviewModal';
import { fromBackendQuestion } from '../lib/testShape';
import { deleteTest, getAdminTest, publishTest, returnTest } from '../../../../api/tests.api';
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

const VISIBILITY_OPTIONS = [
  { value: '',      label: 'Все' },
  { value: 'true',  label: 'Активные' },
  { value: 'false', label: 'Скрытые' },
];

const MODERATION_STATUS_OPTIONS = [
  { value: '',              label: 'Все статусы' },
  { value: 'draft',         label: 'Черновик' },
  { value: 'in_review',     label: 'На проверке' },
  { value: 'published',     label: 'Опубликован' },
  { value: 'needs_changes', label: 'Нужны правки' },
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

  const [actionError, setActionError]   = useState('');
  const [publishingUuid, setPublishingUuid] = useState(null);
  const [returnTarget, setReturnTarget] = useState(null);   // item для диалога возврата
  const [returnReason, setReturnReason] = useState('');
  const [returning, setReturning]       = useState(false);
  const [returnError, setReturnError]   = useState('');

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

  async function handlePublish(item) {
    if (publishingUuid) return;
    setActionError('');
    setPublishingUuid(item.uuid);
    try {
      await publishTest(item.uuid);
      refetch();
    } catch (err) {
      setActionError(err.message || 'Не удалось опубликовать тест');
    } finally {
      setPublishingUuid(null);
    }
  }

  function openReturnDialog(item) {
    setReturnTarget(item);
    setReturnReason('');
    setReturnError('');
  }

  async function handleReturnConfirm() {
    if (!returnTarget || returning) return;
    setReturning(true);
    setReturnError('');
    try {
      await returnTest(returnTarget.uuid, returnReason.trim() || undefined);
      setReturnTarget(null);
      refetch();
    } catch (err) {
      setReturnError(err.message || 'Не удалось вернуть тест на доработку');
    } finally {
      setReturning(false);
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
          style={{ minWidth: 150 }}
          value={filters.status ?? ''}
          options={MODERATION_STATUS_OPTIONS}
          onChange={(val) => setFilters({ status: val || null })}
          placeholder="Все статусы"
        />
        <Select
          style={{ minWidth: 140 }}
          value={filters.is_active === null ? '' : String(filters.is_active)}
          options={VISIBILITY_OPTIONS}
          onChange={(val) => setFilters({ is_active: val === '' ? null : val === 'true' })}
          placeholder="Видимость"
        />
      </div>

      {previewError && (
        <p className={styles.previewError} role="alert">{previewError}</p>
      )}
      {actionError && (
        <p className={styles.previewError} role="alert">{actionError}</p>
      )}

      <TestsTable
        items={items}
        loading={loading}
        error={error}
        onPreview={handlePreview}
        onEdit={(item) => navigate(`/admin/tests/${item.uuid}`)}
        onDelete={(item) => { setDeleteTarget(item); setDeleteError(''); }}
        onPublish={handlePublish}
        onReturn={openReturnDialog}
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

      {returnTarget && (
        <div className={styles.overlay} onClick={() => !returning && setReturnTarget(null)}>
          <div className={styles.dialog} onClick={(e) => e.stopPropagation()}>
            <h3 className={styles.dialogTitle}>Вернуть на доработку?</h3>
            <p className={styles.dialogBody}>
              «{returnTarget.title}» вернётся автору со статусом «Нужны правки».
            </p>
            <textarea
              className={styles.returnReasonInput}
              rows={3}
              placeholder="Комментарий автору (необязательно)"
              value={returnReason}
              onChange={(e) => setReturnReason(e.target.value)}
            />
            {returnError && <p className={styles.dialogError}>{returnError}</p>}
            <div className={styles.dialogActions}>
              <Button variant="secondary" onClick={() => setReturnTarget(null)} disabled={returning}>
                Отмена
              </Button>
              <Button variant="primary" onClick={handleReturnConfirm} disabled={returning}>
                {returning ? 'Отправка…' : 'Вернуть на доработку'}
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
