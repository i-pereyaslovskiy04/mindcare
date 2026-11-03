import Badge from '../../../../components/UI/Badge/Badge';
import AuditLogView from './AuditLogView';
import { ActorCell, RoleAtEventCell, TargetCell } from './AuditTableShell';
import { formatMoscowDateTime } from '../lib/auditFormatters';
import { ROLE_LABELS } from '../../../../shared/lib/roles';
import {
  AUDIT_EVENT_LABELS, OUTCOME_LABELS, OUTCOME_TONES, labelFor,
} from '../lib/auditLabels';
import styles from './AuditTableShell.module.css';

const eventLabel = (item) => labelFor(AUDIT_EVENT_LABELS, item.event_code);

function Outcome({ outcome }) {
  return (
    <Badge tone={OUTCOME_TONES[outcome] ?? 'neutral'}>
      {labelFor(OUTCOME_LABELS, outcome, outcome)}
    </Badge>
  );
}

const COLUMNS = [
  { key: 'time', label: 'Время', className: styles.time, render: (item) => formatMoscowDateTime(item.occurred_at) },
  { key: 'actor', label: 'Участник', render: (item) => <ActorCell actor={item.actor} /> },
  { key: 'role', label: 'Роль действия', render: (item) => <RoleAtEventCell role={item.actor?.role_at_event} /> },
  {
    key: 'event',
    label: 'Действие',
    render: (item) => (
      <>
        <span className={styles.eventLabel}>{eventLabel(item)}</span>
        {item.details_redacted && <span className={styles.redacted}>Часть данных скрыта</span>}
      </>
    ),
  },
  { key: 'target', label: 'Объект', render: (item) => <TargetCell target={item.target} /> },
  {
    key: 'outcome',
    label: 'Результат',
    render: (item) => (item.outcome
      ? <Outcome outcome={item.outcome} />
      : <span className={styles.actorMuted}>—</span>),
  },
];

/** Запись списка (< 56rem): кто, над чем, с каким исходом; роль — мелкой строкой. */
function record(item) {
  const role = item.actor?.role_at_event;
  return {
    time: formatMoscowDateTime(item.occurred_at),
    event: eventLabel(item),
    redacted: item.details_redacted,
    result: item.outcome ? <Outcome outcome={item.outcome} /> : null,
    actor: <ActorCell actor={item.actor} />,
    target: item.target ? <TargetCell target={item.target} /> : null,
    meta: role ? [{ label: 'Роль действия', value: ROLE_LABELS[role] ?? role }] : [],
    detailsLabel: `Подробнее о событии «${eventLabel(item)}» от ${formatMoscowDateTime(item.occurred_at)}`,
  };
}

/** Журнал `audit_log` — семантические события: кто, над чем, с каким исходом. */
export default function AuditEventsTable({ items, loading, error, onRetry, onOpenDetails }) {
  return (
    <AuditLogView
      caption="Журнал действий"
      columns={COLUMNS}
      record={record}
      items={items}
      loading={loading}
      error={error}
      emptyText="За выбранный период с текущими фильтрами событий не найдено"
      onRetry={onRetry}
      onOpenDetails={onOpenDetails}
    />
  );
}
