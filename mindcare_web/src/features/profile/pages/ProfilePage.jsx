import { useAuth, useLogout } from '../../auth/AuthContext';
import CabinetSwitcher from '../../auth/CabinetSwitcher';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import {
  ROLE_LABELS,
  ROLE_BADGE_TONES,
  normalizeRoles,
} from '../../../shared/lib/roles';
import useMyStudentVerification from '../../studentVerification/hooks/useMyStudentVerification';
import {
  VERIFIED_BADGE_LABEL,
  canUseVerificationSelfService,
} from '../../studentVerification/lib/status';
import styles from './ProfilePage.module.css';

export default function ProfilePage() {
  const { user, activeRole, isImpersonating } = useAuth();
  const logout = useLogout();

  // Все активные роли — источник истины `roles[]` (явный [] тоже валиден).
  const roles = normalizeRoles(user);

  // ADR-029: «Студент ДонГУ подтверждён» — отдельный статус, не роль.
  // Запрашивается только для чистого student вне режима «под именем».
  const verification = useMyStudentVerification(
    Boolean(user) && canUseVerificationSelfService(roles, isImpersonating),
  );

  if (!user) return null;

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
          {verification.data?.status === 'approved' && (
            <Badge tone="success">{VERIFIED_BADGE_LABEL}</Badge>
          )}
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
