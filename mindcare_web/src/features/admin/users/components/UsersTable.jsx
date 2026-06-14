import Icon from '../../../../components/Icon/Icon';
import Button from '../../../../components/UI/Button/Button';
import Badge from '../../../../components/UI/Badge/Badge';
import { ROLE_LABELS, ROLE_BADGE_TONES } from '../roleLabels';
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

export default function UsersTable({ items, loading, error, onEdit, onDelete }) {
  const cols = 7; // ФИО, Email, Роль, Статус, Регистрация, Вход, Действия

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
                <Badge tone={ROLE_BADGE_TONES[item.role] ?? 'neutral'}>
                  {ROLE_LABELS[item.role] ?? item.role}
                </Badge>
              </td>
              <td>
                {item.deleted_at ? (
                  <Badge tone="neutral">Удалён</Badge>
                ) : (
                  <Badge tone={item.is_active ? 'success' : 'error'}>
                    {item.is_active ? 'Активен' : 'Заблокирован'}
                  </Badge>
                )}
              </td>
              <td className={styles.date}>{formatDate(item.created_at)}</td>
              <td className={styles.date}>{formatDate(item.last_login)}</td>
              <td className={styles.actionsCell}>
                <div className={styles.actions}>
                  {!item.deleted_at && (
                    <>
                      <Button
                        variant="icon"
                        size="sm"
                        onClick={() => onEdit?.(item)}
                        aria-label={`Редактировать ${item.full_name}`}
                      >
                        <Icon name="edit" size={15} />
                      </Button>
                      <Button
                        variant="icon"
                        size="sm"
                        tone="danger"
                        onClick={() => onDelete?.(item)}
                        aria-label={`Удалить ${item.full_name}`}
                      >
                        <Icon name="trash" size={15} />
                      </Button>
                    </>
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
