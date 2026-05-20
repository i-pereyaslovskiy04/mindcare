import { useAuth } from '../../auth/AuthContext';
import styles from './ProfilePage.module.css';

const ROLE_LABELS = {
  student:      'Студент',
  psychologist: 'Психолог',
  admin:        'Администратор',
  supervisor:   'Супервизор',
};

export default function ProfilePage() {
  const { user, logout } = useAuth();

  if (!user) return null;

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.avatar} aria-hidden="true">
          {(user.name ?? '?').charAt(0).toUpperCase()}
        </div>

        <h1 className={styles.name}>{user.name}</h1>
        <p className={styles.email}>{user.email}</p>

        <div className={styles.badge}>
          {ROLE_LABELS[user.role] ?? user.role}
        </div>

        <button type="button" className={styles.logoutBtn} onClick={logout}>
          Выйти из системы
        </button>
      </div>
    </div>
  );
}
