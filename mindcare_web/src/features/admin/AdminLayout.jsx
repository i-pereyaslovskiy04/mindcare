import { useEffect } from 'react';
import { useLocation, Outlet, NavLink } from 'react-router-dom';
import { useAuth, useLogout } from '../auth/AuthContext';
import CabinetSwitcher from '../auth/CabinetSwitcher';
import Icon from '../../components/Icon/Icon';
import Button from '../../components/UI/Button/Button';
import { getInitials } from '../../shared/lib/utils';
import { normalizeRoles } from '../../shared/lib/roles';
import styles from './AdminLayout.module.css';

const CRUMB_LABELS = {
  '/admin/users':         'Пользователи',
  '/admin/categories':    'Типы материалов',
  '/admin/tags':          'Темы',
  '/admin/news':          'Новости',
  '/admin/articles':      'Материалы',
  '/admin/tests':         'Тесты',
  '/admin/meeting-types': 'Типы встреч',
  '/admin/settings':      'Настройки',
};

export default function AdminLayout() {
  const { pathname } = useLocation();
  const { user, activeRole, setActiveRole } = useAuth();
  const logout = useLogout();
  const crumb = CRUMB_LABELS[pathname] ?? 'Панель';

  // Синхронизируем activeRole с открытым admin-кабинетом (прямой URL/reload).
  useEffect(() => {
    if (activeRole !== 'admin' && normalizeRoles(user).includes('admin')) {
      setActiveRole('admin');
    }
  }, [activeRole, user, setActiveRole]);

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
              <CabinetSwitcher currentRole="admin" />
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

          <NavLink
            to="/admin/meeting-types"
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.active : ''}`
            }
          >
            <span className={styles.navIcon}>
              <Icon name="calendar" size={18} />
            </span>
            <span className={styles.navLabel}>Типы встреч</span>
          </NavLink>

          <NavLink
            to="/admin/tests"
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.active : ''}`
            }
          >
            <span className={styles.navIcon}>
              <Icon name="tests" size={18} />
            </span>
            <span className={styles.navLabel}>Тесты</span>
          </NavLink>

          <div className={styles.navSectionLabel} style={{ marginTop: 14 }}>Аккаунт</div>

          <NavLink
            to="/admin/settings"
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.active : ''}`
            }
          >
            <span className={styles.navIcon}>
              <Icon name="settings" size={18} />
            </span>
            <span className={styles.navLabel}>Настройки</span>
          </NavLink>
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
            {/* Дублирует switcher из sidebar .userInfo, но видим только
                когда sidebar свёрнут в icon-rail (<=980px). */}
            <div className={styles.topbarSwitcher}>
              <CabinetSwitcher currentRole="admin" />
            </div>
            <Button
              type="button"
              variant="icon"
              size="sm"
              aria-label="Выйти"
              onClick={logout}
            >
              <Icon name="logout" size={16} />
            </Button>
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
