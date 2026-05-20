import styles from './UsersTable.module.css';

const ROLE_LABELS = {
  student: 'Студент',
  psychologist: 'Психолог',
  admin: 'Администратор',
  supervisor: 'Супервизор',
};

const SKELETON_ROWS = 7;

function SkeletonRow() {
  return (
    <tr>
      <td><span className={styles.skeletonCell} /></td>
      <td><span className={styles.skeletonCell} style={{ width: '70%' }} /></td>
      <td><span className={styles.skeletonCell} style={{ width: '72px' }} /></td>
      <td><span className={styles.skeletonCell} style={{ width: '84px' }} /></td>
      <td><span className={styles.skeletonCell} style={{ width: '80px' }} /></td>
      <td><span className={styles.skeletonCell} style={{ width: '80px' }} /></td>
    </tr>
  );
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('ru-RU');
}

export default function UsersTable({ items, loading, error }) {
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
          </tr>
        </thead>
        <tbody>
          {loading && Array.from({ length: SKELETON_ROWS }, (_, i) => (
            <SkeletonRow key={i} />
          ))}

          {!loading && error && (
            <tr>
              <td colSpan={6} className={styles.error}>
                Ошибка загрузки: {error}
              </td>
            </tr>
          )}

          {!loading && !error && items.length === 0 && (
            <tr>
              <td colSpan={6} className={styles.empty}>
                Пользователи не найдены
              </td>
            </tr>
          )}

          {!loading && !error && items.map((item) => (
            <tr key={item.uuid} className={styles.row}>
              <td className={styles.name}>{item.full_name}</td>
              <td className={styles.email}>{item.email}</td>
              <td>
                <span className={`${styles.badge} ${styles[`role_${item.role}`]}`}>
                  {ROLE_LABELS[item.role] ?? item.role}
                </span>
              </td>
              <td>
                <span className={`${styles.badge} ${item.is_active ? styles.statusActive : styles.statusBlocked}`}>
                  {item.is_active ? 'Активен' : 'Заблокирован'}
                </span>
              </td>
              <td className={styles.date}>{formatDate(item.created_at)}</td>
              <td className={styles.date}>{formatDate(item.last_login)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
