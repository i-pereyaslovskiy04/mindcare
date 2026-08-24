import Badge from '../../../../components/UI/Badge/Badge';
import AuditTableShell, { ActorCell, DetailsButton } from './AuditTableShell';
import { formatMoscowDateTime } from '../lib/auditFormatters';
import { AUTH_EVENT_LABELS, FAILURE_CODE_LABELS, labelFor } from '../lib/auditLabels';
import { rowKey } from './rowKey';
import styles from './AuditTableShell.module.css';

const COLUMNS = [
  { key: 'time', label: 'Время' },
  { key: 'actor', label: 'Пользователь' },
  { key: 'event', label: 'Событие' },
  { key: 'result', label: 'Результат' },
  { key: 'reason', label: 'Безопасная причина' },
  { key: 'details', label: 'Подробнее', srOnly: true },
];

/**
 * Журнал `auth_log`.
 *
 * Колонки роли здесь нет намеренно: этот журнал роль актора не хранит вообще, а
 * подстановка текущей роли выдавала бы за исторический факт то, чем она не
 * является (backend по той же причине всегда присылает `role_at_event = null`).
 */
export default function AuthEventsTable({ items, loading, error, onRetry, onOpenDetails }) {
  return (
    <AuditTableShell
      caption="Журнал входов и безопасности"
      columns={COLUMNS}
      loading={loading}
      error={error}
      isEmpty={items.length === 0}
      emptyText="За выбранный период с текущими фильтрами событий не найдено"
      onRetry={onRetry}
    >
      {items.map((item) => (
        <tr key={rowKey(item)}>
          <td className={styles.time}>{formatMoscowDateTime(item.occurred_at)}</td>
          <td>
            <ActorCell actor={item.actor} />
            {item.email_masked && (
              <span className={styles.actorEmail}>{item.email_masked}</span>
            )}
          </td>
          <td>
            <span className={styles.eventLabel}>
              {labelFor(AUTH_EVENT_LABELS, item.event_code)}
            </span>
            {item.details_redacted && (
              <span className={styles.redacted}>Часть данных скрыта</span>
            )}
          </td>
          <td>
            <Badge tone={item.success ? 'success' : 'error'}>
              {item.success ? 'Успешно' : 'Отказ'}
            </Badge>
          </td>
          <td>
            {item.failure_code ? (
              labelFor(FAILURE_CODE_LABELS, item.failure_code, item.failure_code)
            ) : (
              <span className={styles.actorMuted}>—</span>
            )}
          </td>
          <td className={styles.actionsCell}>
            <DetailsButton
              onClick={() => onOpenDetails(item)}
              label={`Подробнее о событии «${labelFor(AUTH_EVENT_LABELS, item.event_code)}» от ${formatMoscowDateTime(item.occurred_at)}`}
            />
          </td>
        </tr>
      ))}
    </AuditTableShell>
  );
}
