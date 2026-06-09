import { useLocation, Outlet, NavLink } from 'react-router-dom';
import { useAuth, useLogout } from '../auth/AuthContext';
import Icon from '../../components/Icon/Icon';
import { getInitials } from '../../shared/lib/utils';
import styles from './AdminLayout.module.css';

const CRUMB_LABELS = {
  '/admin/users':      'Пользователи',
  '/admin/categories': 'Типы материалов',
  '/admin/tags':       'Темы',
  '/admin/news':       'Новости',
  '/admin/articles':   'Материалы',
};

export default function AdminLayout() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const logout = useLogout();
  const crumb = CRUMB_LABELS[pathname] ?? 'Панель';

  return (
    <div className={styles.app}>
      <aside className={styles.sidebar}>

        <div className={styles.brand}>
          <span className={styles.brandShort}>М</span>
          <span className={styles.brandFull}>
            Психо<em>логия</em> ДонГУ
          </span>
          <span className={styles.brandSub}>Панель управления</span>
        </div>

        <div className={styles.user}>
          <div className={styles.avatar}>{getInitials(user?.name)}</div>
          <div className={styles.userInfo}>
            <div className={styles.userName}>{user?.name ?? 'Администратор'}</div>
            <div className={styles.userRole}>
              <span className={styles.roleDot} />
              {user?.role === 'supervisor' ? 'Супервизор' : 'Администратор'}
            </div>
          </div>
        </div>

        <nav className={styles.nav}>
          <div className={styles.navSectionLabel}>Управление</div>

          <NavLink
            to="/admin/users"
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.active : ''}`
            }
          >
            <span className={styles.navIcon}>
              <Icon name="users" size={18} />
            </span>
            <span className={styles.navLabel}>Пользователи</span>
          </NavLink>

          <NavLink
            to="/admin/categories"
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.active : ''}`
            }
          >
            <span className={styles.navIcon}>
              <Icon name="folder" size={18} />
            </span>
            <span className={styles.navLabel}>Типы материалов</span>
          </NavLink>

          <NavLink
            to="/admin/tags"
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.active : ''}`
            }
          >
            <span className={styles.navIcon}>
              <Icon name="tag" size={18} />
            </span>
            <span className={styles.navLabel}>Темы</span>
          </NavLink>

          <NavLink
            to="/admin/news"
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.active : ''}`
            }
          >
            <span className={styles.navIcon}>
              <Icon name="news" size={18} />
            </span>
            <span className={styles.navLabel}>Новости</span>
          </NavLink>

          <NavLink
            to="/admin/articles"
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.active : ''}`
            }
          >
            <span className={styles.navIcon}>
              <Icon name="articles" size={18} />
            </span>
            <span className={styles.navLabel}>Материалы</span>
          </NavLink>

          <span className={styles.navItemDisabled}>
            <span className={styles.navIcon}>
              <Icon name="tests" size={18} />
            </span>
            <span className={styles.navLabel}>Тесты</span>
            <span className={styles.navItemSoon}>скоро</span>
          </span>
        </nav>

        <div className={styles.foot}>
          ФГАОУ ВО «Донецкий государственный университет»
          <br />
          <a href="mailto:support@donnu.ru">support@donnu.ru</a>
        </div>

      </aside>

      <main className={styles.main}>
        <div className={styles.topbar}>
          <div className={styles.crumbs}>
            Администратор / <span>{crumb}</span>
          </div>
          <div className={styles.actions}>
            <button
              type="button"
              className={styles.iconBtn}
              aria-label="Выйти"
              onClick={logout}
            >
              <Icon name="logout" size={16} />
            </button>
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
