import { useAuth, useLogout } from '../../features/auth/AuthContext';
import DashboardLayout from '../../components/layouts/DashboardLayout';
import styles from './SupervisorPage.module.css';

export default function SupervisorPage() {
  const { user } = useAuth();
  const logout = useLogout();

  return (
    <DashboardLayout>
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.badge}>Супервизор</div>
          <h1 className={styles.title}>Кабинет супервизора</h1>
          <p className={styles.name}>{user?.name}</p>
          <p className={styles.notice}>
            Раздел находится в разработке. Скоро здесь появится полноценный
            кабинет супервизора.
          </p>
          <button type="button" className={styles.logoutBtn} onClick={logout}>
            Выйти из системы
          </button>
        </div>
      </div>
    </DashboardLayout>
  );
}
