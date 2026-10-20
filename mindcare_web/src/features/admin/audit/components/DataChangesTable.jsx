import AuditTableShell, {
  ActorCell, DetailsButton, RoleAtEventCell,
} from './AuditTableShell';
import { formatMoscowDateTime } from '../lib/auditFormatters';
import {
  OPERATION_LABELS, TABLE_LABELS, changedFieldLabel, labelFor,
} from '../lib/auditLabels';
import { rowKey } from './rowKey';
import styles from './AuditTableShell.module.css';

const COLUMNS = [
  { key: 'time', label: 'Время' },
  { key: 'actor', label: 'Участник' },
  { key: 'role', label: 'Роль' },
  { key: 'operation', label: 'Операция' },
  { key: 'record', label: 'Таблица и запись' },
  { key: 'fields', label: 'Изменённые поля' },
  { key: 'details', label: 'Подробнее', srOnly: true },
];

/**
 * Журнал `data_change_log` — только ИМЕНА изменённых allowlisted полей.
 *
 * Значения полей backend по умолчанию не отдаёт, поэтому показывать здесь
 * нечего кроме имён; для таблицы `users` вместо record_id приходит безопасная
 * сводка пользователя-цели.
 */
export default function DataChangesTable({ items, loading, error, onRetry, onOpenDetails }) {
  return (
    <AuditTableShell
      caption="Журнал изменённых полей"
      columns={COLUMNS}
      loading={loading}
      error={error}
      isEmpty={items.length === 0}
      emptyText="За выбранный период с текущими фильтрами изменений не найдено"
      onRetry={onRetry}
    >
      {items.map((item) => {
        const tableLabel = item.table_name
          ? labelFor(TABLE_LABELS, item.table_name, item.table_name)
          : '—';

        return (
          <tr key={rowKey(item)}>
            <td className={styles.time}>{formatMoscowDateTime(item.occurred_at)}</td>
            <td><ActorCell actor={item.actor} /></td>
            <td><RoleAtEventCell role={item.actor?.role_at_event} /></td>
            <td>
              {item.operation ? (
                labelFor(OPERATION_LABELS, item.operation, item.operation)
              ) : (
                <span className={styles.actorMuted}>—</span>
              )}
              {item.details_redacted && (
                <span className={styles.redacted}>Часть данных скрыта</span>
              )}
            </td>
            <td>
              <div className={styles.recordRef}>
                <span className={styles.targetType}>{tableLabel}</span>
                {item.target_user ? (
                  <>
                    <span className={styles.actorName}>
                      {item.target_user.display_name_current}
                    </span>
                    <span className={styles.actorEmail}>
                      {item.target_user.email_masked}
                    </span>
                  </>
                ) : (
                  item.record_id != null && (
                    <span className={styles.targetRef}>№ {item.record_id}</span>
                  )
                )}
              </div>
            </td>
            <td>
              {item.changed_fields.length ? (
                <div className={styles.fieldList}>
                  {item.changed_fields.map((field) => (
                    <span key={field} className={styles.fieldItem}>
                      {changedFieldLabel(item.table_name, field)}
                    </span>
                  ))}
                </div>
              ) : (
                <span className={styles.actorMuted}>—</span>
              )}
            </td>
            <td className={styles.actionsCell}>
              <DetailsButton
                onClick={() => onOpenDetails(item)}
                label={`Подробнее об изменении в таблице «${tableLabel}» от ${formatMoscowDateTime(item.occurred_at)}`}
              />
            </td>
          </tr>
        );
      })}
    </AuditTableShell>
  );
}
