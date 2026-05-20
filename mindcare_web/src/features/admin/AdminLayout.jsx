import { useLocation, Outlet, NavLink } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import styles from './AdminLayout.module.css';

const CRUMB_LABELS = {
  '/admin/users': 'Пользователи',
};

export default function AdminLayout() {
  const { pathname } = useLocation();
  const { user, logout } = useAuth();
  const crumb = CRUMB_LABELS[pathname] ?? 'Панель';

  return (
    <div className={styles.app}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <div className={styles.brandName}>MindCare Admin</div>
          <div className={styles.brandSub}>Панель управления</div>
        </div>

        <nav className={styles.nav}>
          <div className={styles.navSectionLabel}>Управление</div>

          <NavLink
            to="/admin/users"
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
            }
          >
            Пользователи
          </NavLink>

          <span className={styles.navItemDisabled}>
            Контент
            <span className={styles.navItemSoon}>скоро</span>
          </span>

          <span className={styles.navItemDisabled}>
            Тесты
            <span className={styles.navItemSoon}>скоро</span>
          </span>
        </nav>

        <div className={styles.sidebarFooter}>
          <button
            type="button"
            className={styles.logoutBtn}
            onClick={logout}
          >
            Выйти
          </button>
        </div>
      </aside>

      <main className={styles.main}>
        <div className={styles.topbar}>
          <div className={styles.crumbs}>
            Администратор / <span>{crumb}</span>
          </div>
          <div className={styles.adminName}>
            {user?.name ?? 'Администратор'}
          </div>
        </div>

        <div className={styles.content}>
          <div className={styles.contentInner}>
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
}
