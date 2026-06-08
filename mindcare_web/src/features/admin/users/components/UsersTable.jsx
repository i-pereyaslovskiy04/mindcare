import Icon from '../../../../components/Icon/Icon';
import styles from './UsersTable.module.css';

const ROLE_LABELS = {
  student:      'Студент',
  psychologist: 'Психолог',
  admin:        'Администратор',
  supervisor:   'Супервизор',
};

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
                <span className={`${styles.badge} ${styles[`role_${item.role}`]}`}>
                  {ROLE_LABELS[item.role] ?? item.role}
                </span>
              </td>
              <td>
                {item.deleted_at ? (
                  <span className={`${styles.badge} ${styles.statusDeleted}`}>Удалён</span>
                ) : (
                  <span className={`${styles.badge} ${item.is_active ? styles.statusActive : styles.statusBlocked}`}>
                    {item.is_active ? 'Активен' : 'Заблокирован'}
                  </span>
                )}
              </td>
              <td className={styles.date}>{formatDate(item.created_at)}</td>
              <td className={styles.date}>{formatDate(item.last_login)}</td>
              <td className={styles.actions}>
                {!item.deleted_at && (
                  <>
                    <button
                      type="button"
                      className={styles.iconBtn}
                      onClick={() => onEdit?.(item)}
                      aria-label={`Редактировать ${item.full_name}`}
                    >
                      <Icon name="edit" size={15} />
                    </button>
                    <button
                      type="button"
                      className={`${styles.iconBtn} ${styles.iconBtnDanger}`}
                      onClick={() => onDelete?.(item)}
                      aria-label={`Удалить ${item.full_name}`}
                    >
                      <Icon name="trash" size={15} />
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
