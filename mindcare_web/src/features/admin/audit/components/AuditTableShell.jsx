import Badge from '../../../../components/UI/Badge/Badge';
import Button from '../../../../components/UI/Button/Button';
import Icon from '../../../../components/Icon/Icon';
import { ROLE_BADGE_TONES, ROLE_LABELS } from '../../../../shared/lib/roles';
import { ACTOR_KIND_LABELS, ENTITY_TYPE_LABELS, labelFor } from '../lib/auditLabels';
import { EMPTY_VALUE } from '../lib/auditFormatters';
import { rowKey } from './rowKey';
import styles from './AuditTableShell.module.css';

const SKELETON_ROWS = 8;

/**
 * Широкое представление журнала (≥ 56rem, см. AuditLogView): плотная
 * семантическая таблица. Колонки задаёт журнал — `columns: [{ key, label,
 * render(item) }]`; последняя колонка «Подробнее» добавляется здесь и
 * закреплена справа (sticky), поэтому кнопка видна, даже если очень длинное
 * значение всё-таки вызовет локальный горизонтальный скролл.
 *
 * Своей ширины у таблицы нет: длинные ФИО, объекты и маскированные email
 * переносятся внутри ячеек, а время не переносится — это ось просмотра журнала.
 * Состояния ошибки и пустой выдачи показывает AuditLogView.
 */
export default function AuditTableShell({
  caption, columns, items, loading, detailsLabel, onOpenDetails,
}) {
  const cols = columns.length + 1;

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={column.className}>{column.label}</th>
            ))}
            <th scope="col" className={styles.actionsCell}>
              <span className="visually-hidden">Подробнее</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {loading && Array.from({ length: SKELETON_ROWS }, (_, row) => (
            <tr key={row}>
              {Array.from({ length: cols }, (__, col) => (
                <td key={col}><span className={styles.skeletonCell} /></td>
              ))}
            </tr>
          ))}

          {!loading && items.map((item) => (
            <tr key={rowKey(item)}>
              {columns.map((column) => (
                <td key={column.key} className={column.className}>{column.render(item)}</td>
              ))}
              <td className={styles.actionsCell}>
                <DetailsButton onClick={() => onOpenDetails(item)} label={detailsLabel(item)} />
              </td>
            </tr>
          ))}
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
 * поэтому подписаны как текущие и не выдаются за исторические. Подпись
 * `currentEmailLabel` нужна там, где рядом показан email на момент события.
 * Класс актора — отдельный блок: следующая за ним строка не склеивается с ним.
 */
export function ActorCell({ actor, currentEmailLabel }) {
  if (!actor || actor.kind !== 'user') {
    return (
      <div className={styles.actor}>
        <span className={styles.actorMuted}>
          {labelFor(ACTOR_KIND_LABELS, actor?.kind, EMPTY_VALUE)}
        </span>
      </div>
    );
  }

  return (
    <div className={styles.actor}>
      <span className={styles.actorName}>
        {actor.display_name_current || EMPTY_VALUE}
      </span>
      {actor.email_masked && (
        <span className={styles.actorEmail}>
          {currentEmailLabel && <span className={styles.emailLabel}>{currentEmailLabel} </span>}
          {actor.email_masked}
        </span>
      )}
      {actor.is_deleted_current && (
        <span className={styles.actorFlag}>
          <Badge tone="neutral">Удалён</Badge>
        </span>
      )}
    </div>
  );
}

/** Email на момент события (журнал входов) — с подписью, чтобы не путать с текущим. */
export function EventEmail({ email }) {
  return (
    <span className={styles.actorEmail}>
      <span className={styles.emailLabel}>Email события: </span>
      {email}
    </span>
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

/** Кнопка «Подробнее» таблицы. Кликабельна только она — не вся строка. */
export function DetailsButton({ onClick, label }) {
  return (
    <Button type="button" variant="icon" size="sm" onClick={onClick} aria-label={label} title={label}>
      <Icon name="eye" size={15} />
    </Button>
  );
}
