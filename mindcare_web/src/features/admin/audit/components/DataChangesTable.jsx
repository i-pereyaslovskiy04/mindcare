import AuditLogView from './AuditLogView';
import { ActorCell, RoleAtEventCell } from './AuditTableShell';
import { formatMoscowDateTime } from '../lib/auditFormatters';
import { ROLE_LABELS } from '../../../../shared/lib/roles';
import {
  OPERATION_LABELS, TABLE_LABELS, changedFieldLabel, labelFor,
} from '../lib/auditLabels';
import styles from './AuditTableShell.module.css';

// В списке (< 56rem) видно столько полей, остальное — «+K» (полный список —
// в таблице и в «Подробнее»).
const FIELDS_VISIBLE = 3;

const tableLabel = (item) => (item.table_name
  ? labelFor(TABLE_LABELS, item.table_name, item.table_name)
  : '—');
const operationLabel = (item) => (item.operation
  ? labelFor(OPERATION_LABELS, item.operation, item.operation)
  : null);

function RecordRef({ item }) {
  return (
    <div className={styles.recordRef}>
      <span className={styles.targetType}>{tableLabel(item)}</span>
      {item.target_user ? (
        <>
          <span className={styles.actorName}>{item.target_user.display_name_current}</span>
          <span className={styles.actorEmail}>{item.target_user.email_masked}</span>
        </>
      ) : (
        item.record_id != null && <span className={styles.targetRef}>№ {item.record_id}</span>
      )}
    </div>
  );
}

function FieldList({ item, limit }) {
  const fields = item.changed_fields;
  const shown = limit ? fields.slice(0, limit) : fields;
  return (
    <div className={styles.fieldList}>
      {shown.map((field) => (
        <span key={field} className={styles.fieldItem}>{changedFieldLabel(item.table_name, field)}</span>
      ))}
      {fields.length > shown.length && (
        <span className={styles.actorMuted}>+{fields.length - shown.length}</span>
      )}
    </div>
  );
}

const COLUMNS = [
  { key: 'time', label: 'Время', className: styles.time, render: (item) => formatMoscowDateTime(item.occurred_at) },
  { key: 'actor', label: 'Участник', render: (item) => <ActorCell actor={item.actor} /> },
  { key: 'role', label: 'Роль', render: (item) => <RoleAtEventCell role={item.actor?.role_at_event} /> },
  {
    key: 'operation',
    label: 'Операция',
    render: (item) => (
      <>
        {operationLabel(item) ?? <span className={styles.actorMuted}>—</span>}
        {item.details_redacted && <span className={styles.redacted}>Часть данных скрыта</span>}
      </>
    ),
  },
  { key: 'record', label: 'Таблица и запись', render: (item) => <RecordRef item={item} /> },
  {
    key: 'fields',
    label: 'Изменённые поля',
    render: (item) => (item.changed_fields.length
      ? <FieldList item={item} />
      : <span className={styles.actorMuted}>—</span>),
  },
];

/**
 * Запись списка (< 56rem): операция — заголовок, «участник → таблица и
 * запись», мелкой строкой роль и изменённые поля (первые N + «+K»).
 */
function record(item) {
  const role = item.actor?.role_at_event;
  const count = item.changed_fields.length;
  return {
    time: formatMoscowDateTime(item.occurred_at),
    event: operationLabel(item) ?? 'Операция не указана',
    redacted: item.details_redacted,
    result: null,
    actor: <ActorCell actor={item.actor} />,
    targetLabel: 'Таблица и запись',
    target: <RecordRef item={item} />,
    meta: [
      role && { label: 'Роль', value: ROLE_LABELS[role] ?? role },
      count > 0 && {
        label: `Изменено полей: ${count}`,
        value: <FieldList item={item} limit={FIELDS_VISIBLE} />,
      },
    ].filter(Boolean),
    detailsLabel: `Подробнее об изменении в таблице «${tableLabel(item)}» от ${formatMoscowDateTime(item.occurred_at)}`,
  };
}

/**
 * Журнал `data_change_log` — только ИМЕНА изменённых allowlisted полей.
 *
 * Значения полей backend по умолчанию не отдаёт, поэтому показывать здесь
 * нечего кроме имён; для таблицы `users` вместо record_id приходит безопасная
 * сводка пользователя-цели.
 */
export default function DataChangesTable({ items, loading, error, onRetry, onOpenDetails }) {
  return (
    <AuditLogView
      caption="Журнал изменённых полей"
      columns={COLUMNS}
      record={record}
      items={items}
      loading={loading}
      error={error}
      emptyText="За выбранный период с текущими фильтрами изменений не найдено"
      onRetry={onRetry}
      onOpenDetails={onOpenDetails}
    />
  );
}
