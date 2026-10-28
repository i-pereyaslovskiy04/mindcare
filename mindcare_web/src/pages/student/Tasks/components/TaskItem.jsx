import { Link } from 'react-router-dom';
import Badge from '../../../../components/UI/Badge/Badge';
import Button from '../../../../components/UI/Button/Button';
import Icon from '../../../../components/Icon/Icon';
import {
  STATUS_LABELS, STATUS_TONES, formatDueDate, formatMoment,
} from '../../../../features/assignments/lib/assignmentFormat';
import styles from './TaskItem.module.css';

export const UNAVAILABLE_NOTE =
  'Сопровождение завершено. Если его возобновят с этим же психологом, задание снова станет доступно.';

/**
 * Задание клиента. Отметка выполнения — кнопка (действие необратимо,
 * подтверждение — на странице); статус меняется только по ответу сервера.
 */
export default function TaskItem({ task, onComplete, pending = false, error = null }) {
  const unavailable = task.status === 'active' && !task.engagement_active;
  const errorId = `task-error-${task.uuid}`;
  const finished = task.status !== 'active';

  return (
    <article
      className={`${styles.item} ${finished ? styles.done : ''}`}
      aria-label={`Задание от ${formatMoment(task.created_at) || 'психолога'}`}
    >
      <div className={styles.head}>
        <div className={styles.badges}>
          {unavailable
            ? <Badge tone="neutral">Недоступно</Badge>
            : <Badge tone={STATUS_TONES[task.status]}>{STATUS_LABELS[task.status]}</Badge>}
          {task.is_overdue && <Badge tone="warning">Просрочено</Badge>}
        </div>
        <span className={styles.author}>{task.psychologist_name}</span>
      </div>

      <p className={styles.text}>{task.text}</p>

      {task.material && (
        <p className={styles.material}>
          <Icon name="articles" size={12} stroke={1.6} />
          <Link to={`/student/materials/${task.material.uuid}`} className={styles.materialLink}>
            {task.material.title}
          </Link>
        </p>
      )}
      {task.material_unavailable && (
        <p className={styles.materialMuted}>Прикреплённый материал больше недоступен.</p>
      )}

      {unavailable && <p className={styles.note}>{UNAVAILABLE_NOTE}</p>}

      <div className={styles.foot}>
        {task.due_date && (
          <span className={styles.footItem}>
            <Icon name="calendar" size={11} stroke={1.6} />
            Срок: {formatDueDate(task.due_date)}
          </span>
        )}
        {task.completed_at && (
          <span className={styles.footItem}>Выполнено {formatMoment(task.completed_at)}</span>
        )}
        {task.cancelled_at && (
          <span className={styles.footItem}>Отменено {formatMoment(task.cancelled_at)}</span>
        )}
        {!task.completed_at && !task.cancelled_at && (
          <span className={styles.footItem}>Выдано {formatMoment(task.created_at)}</span>
        )}
      </div>

      {task.can_complete && (
        <div className={styles.actions}>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            loading={pending}
            onClick={() => onComplete(task)}
            aria-describedby={error ? errorId : undefined}
          >
            {pending ? 'Сохраняем…' : 'Отметить выполненным'}
          </Button>
        </div>
      )}
      {error && <p id={errorId} className={styles.error} role="alert">{error}</p>}
    </article>
  );
}
