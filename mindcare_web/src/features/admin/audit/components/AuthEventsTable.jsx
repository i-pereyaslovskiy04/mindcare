import Badge from '../../../../components/UI/Badge/Badge';
import AuditLogView from './AuditLogView';
import { ActorCell, EventEmail } from './AuditTableShell';
import { formatMoscowDateTime } from '../lib/auditFormatters';
import {
  AUTH_EVENT_LABELS,
  AUTH_METHOD_LABELS,
  FAILURE_CODE_LABELS,
  UNKNOWN_AUTH_METHOD_LABEL,
  labelFor,
} from '../lib/auditLabels';
import styles from './AuditTableShell.module.css';

const eventLabel = (item) => labelFor(AUTH_EVENT_LABELS, item.event_code);
const methodLabel = (item) => (item.auth_method
  ? labelFor(AUTH_METHOD_LABELS, item.auth_method, UNKNOWN_AUTH_METHOD_LABEL)
  : null);
const reasonLabel = (item) => (item.failure_code
  ? labelFor(FAILURE_CODE_LABELS, item.failure_code, item.failure_code)
  : null);
const muted = <span className={styles.actorMuted}>—</span>;

function Result({ success }) {
  return <Badge tone={success ? 'success' : 'error'}>{success ? 'Успешно' : 'Отказ'}</Badge>;
}

/**
 * Пользователь строки: текущие ФИО и email аккаунта и, отдельно, email на
 * момент события. Когда есть оба email, текущий подписан — иначе два адреса
 * выглядели бы дублем.
 */
function AuthUser({ item }) {
  return (
    <>
      <ActorCell actor={item.actor} currentEmailLabel={item.email_masked ? 'Email сейчас:' : undefined} />
      {item.email_masked && <EventEmail email={item.email_masked} />}
    </>
  );
}

const COLUMNS = [
  { key: 'time', label: 'Время', className: styles.time, render: (item) => formatMoscowDateTime(item.occurred_at) },
  { key: 'actor', label: 'Пользователь', render: (item) => <AuthUser item={item} /> },
  {
    key: 'event',
    label: 'Событие',
    render: (item) => (
      <>
        <span className={styles.eventLabel}>{eventLabel(item)}</span>
        {item.details_redacted && <span className={styles.redacted}>Часть данных скрыта</span>}
      </>
    ),
  },
  { key: 'result', label: 'Результат', render: (item) => <Result success={item.success} /> },
  { key: 'method', label: 'Способ входа', render: (item) => methodLabel(item) ?? muted },
  { key: 'reason', label: 'Безопасная причина', render: (item) => reasonLabel(item) ?? muted },
];

/**
 * Запись списка (< 56rem). Объекта у журнала входов нет; способ входа и
 * безопасная причина (при отказе — всегда) — мелкой строкой.
 */
function record(item) {
  return {
    time: formatMoscowDateTime(item.occurred_at),
    event: eventLabel(item),
    redacted: item.details_redacted,
    result: <Result success={item.success} />,
    actorLabel: 'Пользователь',
    actor: <AuthUser item={item} />,
    target: null,
    meta: [
      methodLabel(item) && { label: 'Способ входа', value: methodLabel(item) },
      reasonLabel(item) && { label: 'Причина', value: reasonLabel(item) },
    ].filter(Boolean),
    detailsLabel: `Подробнее о событии «${eventLabel(item)}» от ${formatMoscowDateTime(item.occurred_at)}`,
  };
}

/**
 * Журнал `auth_log`.
 *
 * Колонки роли здесь нет намеренно: этот журнал роль актора не хранит вообще, а
 * подстановка текущей роли выдавала бы за исторический факт то, чем она не
 * является (backend по той же причине всегда присылает `role_at_event = null`).
 */
export default function AuthEventsTable({ items, loading, error, onRetry, onOpenDetails }) {
  return (
    <AuditLogView
      caption="Журнал входов и безопасности"
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
