import { useAuth, useLogout } from '../../auth/AuthContext';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import styles from './ProfilePage.module.css';

const ROLE_LABELS = {
  student:      'Студент',
  psychologist: 'Психолог',
  admin:        'Администратор',
  supervisor:   'Супервизор',
};

const ROLE_BADGE_TONE = {
  student:      'role-student',
  psychologist: 'role-psychologist',
  admin:        'role-admin',
  supervisor:   'role-supervisor',
};

export default function ProfilePage() {
  const { user } = useAuth();
  const logout = useLogout();

  if (!user) return null;

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.avatar} aria-hidden="true">
          {(user.name ?? '?').charAt(0).toUpperCase()}
        </div>

        <h1 className={styles.name}>{user.name}</h1>
        <p className={styles.email}>{user.email}</p>

        <Badge tone={ROLE_BADGE_TONE[user.role] ?? 'neutral'}>
          {ROLE_LABELS[user.role] ?? user.role}
        </Badge>

        <Button type="button" variant="danger" onClick={logout}>
          Выйти из системы
        </Button>
      </div>
    </div>
  );
}
