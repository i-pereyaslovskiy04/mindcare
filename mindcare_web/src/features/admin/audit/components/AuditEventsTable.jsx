import Badge from '../../../../components/UI/Badge/Badge';
import AuditTableShell, {
  ActorCell, DetailsButton, RoleAtEventCell, TargetCell,
} from './AuditTableShell';
import { formatMoscowDateTime } from '../lib/auditFormatters';
import {
  AUDIT_EVENT_LABELS, OUTCOME_LABELS, OUTCOME_TONES, labelFor,
} from '../lib/auditLabels';
import { rowKey } from './rowKey';
import styles from './AuditTableShell.module.css';

const COLUMNS = [
  { key: 'time', label: 'Время' },
  { key: 'actor', label: 'Участник' },
  { key: 'role', label: 'Роль действия' },
  { key: 'event', label: 'Действие' },
  { key: 'target', label: 'Объект' },
  { key: 'outcome', label: 'Результат' },
  { key: 'details', label: 'Подробнее', srOnly: true },
];

/** Журнал `audit_log` — семантические события: кто, над чем, с каким исходом. */
export default function AuditEventsTable({ items, loading, error, onRetry, onOpenDetails }) {
  return (
    <AuditTableShell
      caption="Журнал действий"
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
          <td><ActorCell actor={item.actor} /></td>
          <td><RoleAtEventCell role={item.actor?.role_at_event} /></td>
          <td>
            <span className={styles.eventLabel}>
              {labelFor(AUDIT_EVENT_LABELS, item.event_code)}
            </span>
            {item.details_redacted && (
              <span className={styles.redacted}>Часть данных скрыта</span>
            )}
          </td>
          <td><TargetCell target={item.target} /></td>
          <td>
            {item.outcome ? (
              <Badge tone={OUTCOME_TONES[item.outcome] ?? 'neutral'}>
                {labelFor(OUTCOME_LABELS, item.outcome, item.outcome)}
              </Badge>
            ) : (
              <span className={styles.actorMuted}>—</span>
            )}
          </td>
          <td className={styles.actionsCell}>
            <DetailsButton
              onClick={() => onOpenDetails(item)}
              label={`Подробнее о событии «${labelFor(AUDIT_EVENT_LABELS, item.event_code)}» от ${formatMoscowDateTime(item.occurred_at)}`}
            />
          </td>
        </tr>
      ))}
    </AuditTableShell>
  );
}
