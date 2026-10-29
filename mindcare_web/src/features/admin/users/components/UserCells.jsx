import Badge from '../../../../components/UI/Badge/Badge';
import Button from '../../../../components/UI/Button/Button';
import ActionsMenu from '../../../../components/UI/ActionsMenu/ActionsMenu';
import { ROLE_LABELS, ROLE_BADGE_TONES } from '../roleLabels';
import { selectableRoles } from '../../../../shared/lib/roles';
import { getUserActions } from '../userActions';
import styles from './UserCells.module.css';

/**
 * Доменное содержимое строки пользователя для ResponsiveTable: имя, роли,
 * статус, даты и действия. Раскладку (таблица / строки списка) задаёт
 * shared ResponsiveTable.
 */

export function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('ru-RU');
}

/** ФИО; удалённый ранее — зачёркнут. */
export function UserName({ item }) {
  return item.deleted_at
    ? <span className={styles.deletedName}>{item.full_name}</span>
    : item.full_name;
}

/** Роль student неявно выдана всем staff — в перечне её не показываем (шум).
 *  Чистый студент имеет только student, для него бэдж остаётся. */
export function RoleBadges({ item }) {
  return (
    <span className={styles.roles}>
      {selectableRoles(item).map((role) => (
        <Badge key={role} tone={ROLE_BADGE_TONES[role] ?? 'neutral'}>
          {ROLE_LABELS[role] ?? role}
        </Badge>
      ))}
    </span>
  );
}

export function StatusBadge({ item }) {
  if (item.deleted_at) {
    return <Badge tone="neutral">Отключён (удалён ранее)</Badge>;
  }
  if (item.is_active === false) {
    return (
      <span className={styles.status}>
        <Badge tone="error">Отключён</Badge>
        {item.deactivation_source === 'self' && (
          <span className={styles.statusNote}>по запросу пользователя</span>
        )}
      </span>
    );
  }
  return <Badge tone="success">Активен</Badge>;
}

/** Колонка «Активность» таблицы: регистрация и вход двумя строками. */
export function UserActivity({ item }) {
  return (
    <dl className={styles.activity}>
      <dt>Регистрация</dt>
      <dd>{formatDate(item.created_at)}</dd>
      <dt>Вход</dt>
      <dd>{formatDate(item.last_login)}</dd>
    </dl>
  );
}

/** Основное действие строки кнопкой (матрица — userActions). */
export function UserPrimaryAction({ item, actionContext }) {
  const { primary } = getUserActions(item, actionContext);
  if (!primary) return null;
  return (
    <Button variant="secondary" size="sm" onClick={primary.onSelect} aria-label={primary.ariaLabel}>
      {primary.label}
    </Button>
  );
}

/** Остальные действия строки — меню «⋮»; нет действий — нет кнопки. */
export function UserMoreActions({ item, actionContext }) {
  const { menu } = getUserActions(item, actionContext);
  return <ActionsMenu triggerLabel={`Другие действия: ${item.full_name}`} items={menu} />;
}
