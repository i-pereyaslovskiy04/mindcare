import { useAuth, useLogout } from '../../auth/AuthContext';
import CabinetSwitcher from '../../auth/CabinetSwitcher';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import {
  ROLE_LABELS,
  ROLE_BADGE_TONES,
  normalizeRoles,
} from '../../../shared/lib/roles';
import styles from './ProfilePage.module.css';

export default function ProfilePage() {
  const { user, activeRole } = useAuth();
  const logout = useLogout();

  if (!user) return null;

  // Все активные роли — источник истины `roles[]` (явный [] тоже валиден).
  const roles = normalizeRoles(user);

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.avatar} aria-hidden="true">
          {(user.name ?? '?').charAt(0).toUpperCase()}
        </div>

        <h1 className={styles.name}>{user.name}</h1>
        <p className={styles.email}>{user.email}</p>

        <div className={styles.roles}>
          {roles.map((role) => (
            <Badge key={role} tone={ROLE_BADGE_TONES[role] ?? 'neutral'}>
              {ROLE_LABELS[role] ?? role}
            </Badge>
          ))}
        </div>

        {roles.length > 1 && (
          <div className={styles.switcher}>
            <CabinetSwitcher currentRole={activeRole} />
          </div>
        )}

        <Button type="button" variant="danger" onClick={logout}>
          Выйти из системы
        </Button>
      </div>
    </div>
  );
}
