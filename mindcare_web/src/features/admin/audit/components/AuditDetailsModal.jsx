import Badge from '../../../../components/UI/Badge/Badge';
import Modal from '../../../../components/Modal/Modal';
import { ROLE_LABELS } from '../../../../shared/lib/roles';
import {
  EMPTY_VALUE, formatFileSize, formatMoscowDateTimeLong,
} from '../lib/auditFormatters';
import {
  ACTOR_KIND_LABELS,
  AUDIT_EVENT_LABELS,
  AUTH_EVENT_LABELS,
  DETAIL_KEY_LABELS,
  DETAIL_KEY_ORDER,
  ENTITY_TYPE_LABELS,
  FAILURE_CODE_LABELS,
  FILTER_KEY_LABELS,
  JOURNAL_LABELS,
  OPERATION_LABELS,
  OUTCOME_LABELS,
  OUTCOME_TONES,
  TABLE_LABELS,
  changedFieldLabel,
  labelFor,
} from '../lib/auditLabels';
import styles from './AuditDetailsModal.module.css';

function Row({ label, children }) {
  return (
    <div className={styles.row}>
      <dt className={styles.rowLabel}>{label}</dt>
      <dd className={styles.rowValue}>{children}</dd>
    </div>
  );
}

const joinLabels = (values, map) =>
  (Array.isArray(values) ? values : [])
    .map((value) => map[value] ?? value)
    .join(', ');

/**
 * Значение allowlisted ключа details. Ни один ключ не рендерится «как придёт»:
 * у каждого свой известный тип и своя подача.
 */
function renderDetailValue(key, value) {
  switch (key) {
    case 'journal':
      return labelFor(JOURNAL_LABELS, value, value);
    case 'filter_keys':
      return joinLabels(value, FILTER_KEY_LABELS);
    case 'roles_before':
    case 'roles_after':
    case 'added':
    case 'removed':
      return joinLabels(value, ROLE_LABELS);
    case 'fields':
      return <code className={styles.code}>{(value ?? []).join(', ')}</code>;
    case 'mime_type':
      return <code className={styles.code}>{value}</code>;
    case 'file_size':
      return formatFileSize(value);
    case 'linked_user_uuid':
      return <code className={styles.code}>{value}</code>;
    default:
      return null;
  }
}

function ActorRows({ actor }) {
  if (!actor) return null;

  return (
    <>
      <Row label="Участник">
        {labelFor(ACTOR_KIND_LABELS, actor.kind, EMPTY_VALUE)}
      </Row>
      {actor.kind === 'user' && (
        <>
          <Row label="Текущее ФИО">{actor.display_name_current || EMPTY_VALUE}</Row>
          <Row label="Текущий email">{actor.email_masked || EMPTY_VALUE}</Row>
          {actor.is_deleted_current && (
            <Row label="Состояние аккаунта">
              <Badge tone="neutral">Учётная запись удалена</Badge>
            </Row>
          )}
        </>
      )}
      {actor.role_at_event && (
        <Row label="Роль действия">
          {ROLE_LABELS[actor.role_at_event] ?? actor.role_at_event}
        </Row>
      )}
    </>
  );
}

/**
 * Подробности строки журнала.
 *
 * Строится ИЗ УЖЕ ЗАГРУЖЕННОЙ строки — никакого запроса при открытии: у
 * журналов нет detail-эндпоинта, а чтение фиксируется access-событием, и лишний
 * вызов засорял бы его. Рендерятся только перечисленные поля; неизвестный ключ
 * `details` не показывается вовсе.
 */
export default function AuditDetailsModal({ item, onClose }) {
  const open = Boolean(item);

  return (
    <Modal open={open} onClose={onClose} ariaLabel="Подробности записи журнала" size="md">
      {item && (
        <div className={styles.body}>
          <h2 className={styles.title}>Запись журнала</h2>

          <dl className={styles.list}>
            <Row label="Время">{formatMoscowDateTimeLong(item.occurred_at)}</Row>
            <Row label="Журнал">{labelFor(JOURNAL_LABELS, item.source, item.source)}</Row>

            <ActorRows actor={item.actor} />

            {item.source !== 'data_change_log' && (
              <Row label="Событие">
                <span className={styles.eventLabel}>
                  {labelFor(
                    item.source === 'auth_log' ? AUTH_EVENT_LABELS : AUDIT_EVENT_LABELS,
                    item.event_code,
                  )}
                </span>
                <code className={styles.code}>{item.event_code}</code>
              </Row>
            )}

            {item.source === 'audit_log' && item.outcome && (
              <Row label="Результат">
                <Badge tone={OUTCOME_TONES[item.outcome] ?? 'neutral'}>
                  {labelFor(OUTCOME_LABELS, item.outcome, item.outcome)}
                </Badge>
              </Row>
            )}

            {item.source === 'auth_log' && (
              <Row label="Результат">
                <Badge tone={item.success ? 'success' : 'error'}>
                  {item.success ? 'Успешно' : 'Отказ'}
                </Badge>
              </Row>
            )}

            {item.source === 'auth_log' && item.email_masked && (
              <Row label="Email в момент события">{item.email_masked}</Row>
            )}

            {item.failure_code && (
              <Row label="Причина отказа">
                <span>{labelFor(FAILURE_CODE_LABELS, item.failure_code, item.failure_code)}</span>
                <code className={styles.code}>{item.failure_code}</code>
              </Row>
            )}

            {item.source === 'audit_log' && item.target && (
              <Row label="Объект">
                <span>
                  {labelFor(ENTITY_TYPE_LABELS, item.target.entity_type, item.target.entity_type)}
                </span>
                {item.target.user ? (
                  <span className={styles.sub}>
                    {item.target.user.display_name_current} · {item.target.user.email_masked}
                  </span>
                ) : (
                  item.target.entity_ref != null && (
                    <span className={styles.sub}>№ {item.target.entity_ref}</span>
                  )
                )}
              </Row>
            )}

            {item.source === 'data_change_log' && (
              <>
                <Row label="Операция">
                  {item.operation
                    ? labelFor(OPERATION_LABELS, item.operation, item.operation)
                    : EMPTY_VALUE}
                </Row>
                <Row label="Таблица">
                  {item.table_name
                    ? labelFor(TABLE_LABELS, item.table_name, item.table_name)
                    : EMPTY_VALUE}
                </Row>
                {item.target_user && (
                  <Row label="Запись">
                    <span>{item.target_user.display_name_current}</span>
                    <span className={styles.sub}>{item.target_user.email_masked}</span>
                  </Row>
                )}
                {!item.target_user && item.record_id != null && (
                  <Row label="Запись">№ {item.record_id}</Row>
                )}
                <Row label="Изменённые поля">
                  {item.changed_fields.length
                    ? item.changed_fields
                      .map((field) => changedFieldLabel(item.table_name, field))
                      .join(', ')
                    : EMPTY_VALUE}
                </Row>
              </>
            )}

            {DETAIL_KEY_ORDER.filter(
              (key) => item.details && item.details[key] !== undefined,
            ).map((key) => (
              <Row key={key} label={DETAIL_KEY_LABELS[key]}>
                {renderDetailValue(key, item.details[key])}
              </Row>
            ))}
          </dl>

          {item.details_redacted && (
            <p className={styles.redactedNote}>
              Часть исторических данных скрыта политикой безопасности.
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}
