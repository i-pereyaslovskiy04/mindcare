import Badge from '../../../../components/UI/Badge/Badge';
import Button from '../../../../components/UI/Button/Button';
import Icon from '../../../../components/Icon/Icon';
import { ROLE_BADGE_TONES, ROLE_LABELS } from '../../../../shared/lib/roles';
import { ACTOR_KIND_LABELS, ENTITY_TYPE_LABELS, labelFor } from '../lib/auditLabels';
import { EMPTY_VALUE } from '../lib/auditFormatters';
import styles from './AuditTableShell.module.css';

const SKELETON_ROWS = 8;

function SkeletonRows({ cols }) {
  return Array.from({ length: SKELETON_ROWS }, (_, row) => (
    <tr key={row}>
      {Array.from({ length: cols }, (_, col) => (
        <td key={col}><span className={styles.skeletonCell} /></td>
      ))}
    </tr>
  ));
}

/**
 * Общая обвязка таблиц трёх журналов: заголовки, состояния загрузки/ошибки/
 * пустой выдачи и горизонтальный скролл.
 *
 * Скролл живёт на обёртке таблицы, а не на странице: строки журналов длинные
 * (подпись события + объект + участник), но фильтры и пагинация обязаны
 * оставаться на месте.
 */
export default function AuditTableShell({
  caption,
  columns,
  loading,
  error,
  isEmpty,
  emptyText,
  onRetry,
  children,
}) {
  const cols = columns.length;

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <caption className={styles.caption}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={column.srOnly ? styles.srOnlyHead : undefined}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && <SkeletonRows cols={cols} />}

          {!loading && error && (
            <tr>
              <td colSpan={cols} className={styles.state}>
                <p className={styles.errorText}>{error}</p>
                {onRetry && (
                  <Button type="button" variant="secondary" size="sm" onClick={onRetry}>
                    Повторить
                  </Button>
                )}
              </td>
            </tr>
          )}

          {!loading && !error && isEmpty && (
            <tr>
              <td colSpan={cols} className={styles.state}>
                {emptyText}
              </td>
            </tr>
          )}

          {!loading && !error && !isEmpty && children}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Участник строки журнала.
 *
 * `system` / `anonymous` / `unavailable` — полноценные классы актора, а не
 * «пусто»: у них нет и не может быть ни имени, ни email. ФИО и email
 * пользователя — ТЕКУЩЕЕ состояние аккаунта, а не снимок на момент события,
 * поэтому подписаны как текущие и не выдаются за исторические.
 */
export function ActorCell({ actor }) {
  if (!actor || actor.kind !== 'user') {
    return (
      <span className={styles.actorMuted}>
        {labelFor(ACTOR_KIND_LABELS, actor?.kind, EMPTY_VALUE)}
      </span>
    );
  }

  return (
    <div className={styles.actor}>
      <span className={styles.actorName}>
        {actor.display_name_current || EMPTY_VALUE}
      </span>
      {actor.email_masked && (
        <span className={styles.actorEmail}>{actor.email_masked}</span>
      )}
      {actor.is_deleted_current && (
        <span className={styles.actorFlag}>
          <Badge tone="neutral">Удалён</Badge>
        </span>
      )}
    </div>
  );
}

/** Роль, с которой действовал участник. Берётся из строки журнала, не из сессии. */
export function RoleAtEventCell({ role }) {
  if (!role) return <span className={styles.actorMuted}>{EMPTY_VALUE}</span>;
  return (
    <Badge tone={ROLE_BADGE_TONES[role] ?? 'neutral'}>
      {ROLE_LABELS[role] ?? role}
    </Badge>
  );
}

/**
 * Объект действия. Для цели-человека backend всегда присылает `entity_ref=null`
 * — внутренний users.id наружу не выходит, показываем безопасную сводку.
 */
export function TargetCell({ target }) {
  if (!target) return <span className={styles.actorMuted}>{EMPTY_VALUE}</span>;

  return (
    <div className={styles.target}>
      <span className={styles.targetType}>
        {labelFor(ENTITY_TYPE_LABELS, target.entity_type, target.entity_type)}
      </span>
      {target.user ? (
        <>
          <span className={styles.actorName}>{target.user.display_name_current}</span>
          <span className={styles.actorEmail}>{target.user.email_masked}</span>
        </>
      ) : (
        target.entity_ref != null && (
          <span className={styles.targetRef}>№ {target.entity_ref}</span>
        )
      )}
    </div>
  );
}

/** Кнопка «Подробнее». Кликабельна только она — не вся строка. */
export function DetailsButton({ onClick, label }) {
  return (
    <Button type="button" variant="icon" size="sm" onClick={onClick} aria-label={label} title={label}>
      <Icon name="eye" size={15} />
    </Button>
  );
}
