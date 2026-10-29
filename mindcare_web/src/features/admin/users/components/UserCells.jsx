import Badge from '../../../../components/UI/Badge/Badge';
import Button from '../../../../components/UI/Button/Button';
import ActionsMenu from '../../../../components/UI/ActionsMenu/ActionsMenu';
import { ROLE_LABELS, ROLE_BADGE_TONES } from '../roleLabels';
import { selectableRoles } from '../../../../shared/lib/roles';
import { getUserActions } from '../userActions';
import styles from './UserCells.module.css';

/**
 * Общие части строки пользователя — одинаковы в таблице и компактном списке.
 */

export function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('ru-RU');
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

/** Основное действие кнопкой + остальные в меню «⋮» (матрица — userActions). */
export function UserRowActions({ item, actionContext, className }) {
  const { primary, menu } = getUserActions(item, actionContext);
  return (
    <div className={[styles.actions, className].filter(Boolean).join(' ')}>
      {primary && (
        <Button
          variant="secondary"
          size="sm"
          className={styles.primary}
          onClick={primary.onSelect}
          aria-label={primary.ariaLabel}
        >
          {primary.label}
        </Button>
      )}
      <ActionsMenu triggerLabel={`Другие действия: ${item.full_name}`} items={menu} />
    </div>
  );
}
