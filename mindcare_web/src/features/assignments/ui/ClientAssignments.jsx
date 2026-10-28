import { useState } from 'react';
import { Link } from 'react-router-dom';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import useClientAssignments from '../hooks/useClientAssignments';
import {
  STATUS_LABELS, STATUS_TONES, formatDueDate, formatMoment,
} from '../lib/assignmentFormat';
import AssignmentForm from './AssignmentForm';
import ConfirmDialog from './ConfirmDialog';
import styles from './ClientAssignments.module.css';

function AssignmentRow({ item, onCancel, pending, error }) {
  const errorId = `assignment-error-${item.uuid}`;
  return (
    <li className={styles.item}>
      <div className={styles.itemHead}>
        <div className={styles.badges}>
          <Badge tone={STATUS_TONES[item.status]}>{STATUS_LABELS[item.status]}</Badge>
          {item.is_overdue && <Badge tone="warning">Просрочено</Badge>}
        </div>
        <span className={styles.meta}>Выдано {formatMoment(item.created_at)}</span>
      </div>
      <p className={styles.text}>{item.text}</p>
      {item.material && (
        <p className={styles.meta}>
          Материал:{' '}
          <Link to={`/psychologist/materials/${item.material.uuid}`} className={styles.materialLink}>
            {item.material.title}
          </Link>
        </p>
      )}
      {item.material_unavailable && (
        <p className={styles.meta}>Прикреплённый материал больше недоступен.</p>
      )}
      <div className={styles.itemFoot}>
        <span className={styles.meta}>
          {item.due_date ? `Срок: ${formatDueDate(item.due_date)}` : 'Без срока'}
          {item.completed_at && ` · Выполнено ${formatMoment(item.completed_at)}`}
          {item.cancelled_at && ` · Отменено ${formatMoment(item.cancelled_at)}`}
        </span>
        {item.can_cancel && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            loading={pending}
            onClick={() => onCancel(item)}
            aria-describedby={error ? errorId : undefined}
          >
            Отменить
          </Button>
        )}
      </div>
      {error && <p id={errorId} className={styles.error} role="alert">{error}</p>}
    </li>
  );
}

/**
 * Раздел «Задания» в карточке клиента: выдача, список со статусами, отмена.
 * Только текущее строгое сопровождение; чтение фиксируется backend'ом.
 */
export default function ClientAssignments({ studentUuid }) {
  const {
    list, status, reload, create, submitting, formError,
    cancel, pendingUuid, actionError,
  } = useClientAssignments(studentUuid);
  const [confirmItem, setConfirmItem] = useState(null);

  if (status === 'unavailable') {
    return <p className={styles.muted}>Задания недоступны: сопровождение не активно.</p>;
  }

  async function confirmCancel() {
    if (!confirmItem) return;
    await cancel(confirmItem.uuid);
    setConfirmItem(null);
  }

  const orphanError = actionError && !list.items.some(i => i.uuid === actionError.uuid)
    ? actionError.message : null;

  return (
    <div className={styles.wrap}>
      <AssignmentForm onCreate={create} submitting={submitting} formError={formError} />

      {orphanError && <p className={styles.error} role="alert">{orphanError}</p>}

      {status === 'loading' && <p className={styles.muted} role="status">Загружаем задания…</p>}

      {(status === 'error' || status === 'auditUnavailable') && (
        <div className={styles.errorBox} role="alert">
          <p className={styles.error}>
            {status === 'auditUnavailable'
              ? 'Не удалось зафиксировать просмотр заданий — список не показан. Повторите попытку.'
              : 'Не удалось загрузить задания.'}
          </p>
          <Button type="button" size="sm" variant="secondary" onClick={reload}>
            Повторить
          </Button>
        </div>
      )}

      {status === 'ready' && list.items.length === 0 && (
        <p className={styles.muted}>Заданий пока нет.</p>
      )}

      {list.items.length > 0 && status !== 'error' && status !== 'auditUnavailable' && (
        <ul className={styles.list} aria-label="Выданные задания">
          {list.items.map(item => (
            <AssignmentRow
              key={item.uuid}
              item={item}
              onCancel={setConfirmItem}
              pending={pendingUuid === item.uuid}
              error={actionError?.uuid === item.uuid ? actionError.message : null}
            />
          ))}
        </ul>
      )}

      {list.loadMoreError && (
        <p className={styles.error} role="alert">
          {list.loadMoreError.status === 503
            ? 'Не удалось зафиксировать просмотр следующих заданий — они не показаны. Повторите попытку.'
            : 'Не удалось загрузить следующие задания. Проверьте соединение и нажмите «Показать ещё».'}
        </p>
      )}
      {list.hasMore && !list.error && (
        <div className={styles.more}>
          <Button type="button" variant="secondary" size="sm" onClick={list.loadMore}
            loading={list.loadingMore}>
            Показать ещё
          </Button>
        </div>
      )}

      <ConfirmDialog
        open={confirmItem !== null}
        title="Отменить задание?"
        description="Отменённое задание нельзя вернуть. Чтобы заменить его, выдайте новое."
        confirmLabel="Отменить задание"
        confirmTone="danger"
        loading={confirmItem !== null && pendingUuid === confirmItem.uuid}
        onConfirm={confirmCancel}
        onClose={() => setConfirmItem(null)}
      />
    </div>
  );
}
