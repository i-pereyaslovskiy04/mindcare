import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { ROLE_PRIORITY, ROLE_LABELS, normalizeRoles } from '../../shared/lib/roles';
import { getRoleHome } from '../../shared/lib/routes';
import styles from './RoleChooser.module.css';

/**
 * Экран выбора кабинета для multi-role пользователя (ADR-018).
 * Рендерится DashboardRedirect'ом, когда у пользователя несколько ролей и нет
 * валидного сохранённого activeRole. Выбор — только UI-hint; доступ к маршруту
 * всё равно проверяет RoleRoute + backend.
 */
export default function RoleChooser({ roles }) {
  const navigate = useNavigate();
  const { user, setActiveRole } = useAuth();

  // Источник истины — нормализованные роли пользователя; проп roles — подсказка.
  const memberRoles = normalizeRoles(user);
  const list = ROLE_PRIORITY.filter(
    (r) => memberRoles.includes(r) && (!roles || roles.includes(r)),
  );

  const choose = (role) => {
    setActiveRole(role);
    navigate(getRoleHome(role), { replace: true });
  };

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <h1 className={styles.title}>Выберите кабинет</h1>
        <p className={styles.subtitle}>
          У вашей учётной записи несколько ролей. Выберите, в каком кабинете
          продолжить — позже можно переключиться.
        </p>
        <div className={styles.grid}>
          {list.map((role) => (
            <button
              key={role}
              type="button"
              className={styles.option}
              onClick={() => choose(role)}
            >
              {ROLE_LABELS[role] ?? role}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
