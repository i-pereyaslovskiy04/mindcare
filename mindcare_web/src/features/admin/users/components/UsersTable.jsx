import Icon from '../../../../components/Icon/Icon';
import Button from '../../../../components/UI/Button/Button';
import Badge from '../../../../components/UI/Badge/Badge';
import { ROLE_LABELS, ROLE_BADGE_TONES } from '../roleLabels';
import { selectableRoles as rolesForBadges } from '../../../../shared/lib/roles';
import styles from './UsersTable.module.css';

const SKELETON_ROWS = 7;

function SkeletonRow({ cols }) {
  return (
    <tr>
      {Array.from({ length: cols }, (_, i) => (
        <td key={i}><span className={styles.skeletonCell} /></td>
      ))}
    </tr>
  );
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('ru-RU');
}

/** Отключён = is_active=false ИЛИ исторически soft-deleted (ADR-028). */
export function isDisabled(item) {
  return Boolean(item.deleted_at) || item.is_active === false;
}

function StatusBadge({ item }) {
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

export default function UsersTable({
  items, loading, error, onEdit, onDeactivate, onRestore, onImpersonate,
  currentUserId,
}) {
  const cols = 7; // ФИО, Email, Роль, Статус, Регистрация, Вход, Действия

  // «Зайти под именем» доступно только для активного не-удалённого не-админа
  // и не самого себя (backend дублирует guard — defense-in-depth, ADR-025).
  const canImpersonate = (item) =>
    !isDisabled(item) &&
    !(item.roles || []).includes('admin') &&
    item.id !== currentUserId;

  // Собственный аккаунт администратора отключить нельзя (backend отвечает
  // 422 self_admin_protected) — действие не показывается вовсе.
  const canDeactivate = (item) => !isDisabled(item) && item.id !== currentUserId;

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>ФИО</th>
            <th>Email</th>
            <th>Роль</th>
            <th>Статус</th>
            <th>Дата регистрации</th>
            <th>Последний вход</th>
            <th aria-label="Действия" />
          </tr>
        </thead>
        <tbody>
          {loading && Array.from({ length: SKELETON_ROWS }, (_, i) => (
            <SkeletonRow key={i} cols={cols} />
          ))}

          {!loading && error && (
            <tr>
              <td colSpan={cols} className={styles.error}>
                Ошибка загрузки: {error}
              </td>
            </tr>
          )}

          {!loading && !error && items.length === 0 && (
            <tr>
              <td colSpan={cols} className={styles.empty}>
                Пользователи не найдены
              </td>
            </tr>
          )}

          {!loading && !error && items.map((item) => (
            <tr key={item.uuid} className={`${styles.row}${item.deleted_at ? ` ${styles.rowDeleted}` : ''}`}>
              <td className={styles.name}>{item.full_name}</td>
              <td className={styles.email}>{item.email}</td>
              <td>
                <div className={styles.roles}>
                  {/* Роль student неявно выдана всем staff — в перечне ролей
                      /admin/users её не показываем (шум). Чистый студент имеет
                      только student, для него бэдж остаётся. */}
                  {rolesForBadges(item).map((role) => (
                    <Badge key={role} tone={ROLE_BADGE_TONES[role] ?? 'neutral'}>
                      {ROLE_LABELS[role] ?? role}
                    </Badge>
                  ))}
                </div>
              </td>
              <td>
                <StatusBadge item={item} />
              </td>
              <td className={styles.date}>{formatDate(item.created_at)}</td>
              <td className={styles.date}>{formatDate(item.last_login)}</td>
              <td className={styles.actionsCell}>
                <div className={styles.actions}>
                  {/* Редактирование доступно и отключённому (не удалённому)
                      аккаунту; lifecycle — отдельные действия. */}
                  {!item.deleted_at && (
                    <>
                      {canImpersonate(item) && (
                        <Button
                          variant="icon"
                          size="sm"
                          onClick={() => onImpersonate?.(item)}
                          aria-label={`Зайти под именем ${item.full_name}`}
                          title="Зайти под именем"
                        >
                          <Icon name="arrow-right" size={15} />
                        </Button>
                      )}
                      <Button
                        variant="icon"
                        size="sm"
                        onClick={() => onEdit?.(item)}
                        aria-label={`Редактировать ${item.full_name}`}
                        title="Редактировать"
                      >
                        <Icon name="edit" size={15} />
                      </Button>
                    </>
                  )}
                  {canDeactivate(item) && (
                    <Button
                      variant="icon"
                      size="sm"
                      tone="danger"
                      onClick={() => onDeactivate?.(item)}
                      aria-label={`Отключить аккаунт ${item.full_name}`}
                      title="Отключить аккаунт"
                    >
                      <Icon name="power" size={15} />
                    </Button>
                  )}
                  {isDisabled(item) && (
                    <Button
                      variant="icon"
                      size="sm"
                      tone="success"
                      onClick={() => onRestore?.(item)}
                      aria-label={`Восстановить ${item.full_name}`}
                      title="Восстановить"
                    >
                      <Icon name="undo" size={15} />
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
