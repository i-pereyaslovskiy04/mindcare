import { useEffect } from 'react';
import { useLocation, Outlet, NavLink } from 'react-router-dom';
import { useAuth, useLogout } from '../auth/AuthContext';
import CabinetSwitcher from '../auth/CabinetSwitcher';
import Icon from '../../components/Icon/Icon';
import Button from '../../components/UI/Button/Button';
import ThemeToggle from '../theme/ThemeToggle';
import A11yToggle from '../a11y/A11yToggle';
import A11yPanel from '../a11y/A11yPanel';
import { getInitials } from '../../shared/lib/utils';
import { normalizeRoles } from '../../shared/lib/roles';
import styles from './AdminLayout.module.css';

const ADMIN_NAV_GROUPS = [
  {
    label: 'Управление',
    items: [
      { label: 'Пользователи', path: '/admin/users', icon: 'users' },
    ],
  },
  {
    label: 'Контент',
    items: [
      { label: 'Материалы', path: '/admin/articles', icon: 'articles' },
      { label: 'Новости',   path: '/admin/news',     icon: 'news' },
      { label: 'Тесты',     path: '/admin/tests',    icon: 'tests' },
      { label: 'Баннер',    path: '/admin/banner-slides', icon: 'image' },
    ],
  },
  {
    label: 'Система',
    items: [
      { label: 'Типы материалов',    path: '/admin/categories',    icon: 'folder' },
      { label: 'Темы',               path: '/admin/tags',          icon: 'tag' },
      { label: 'Типы встреч',        path: '/admin/meeting-types', icon: 'calendar' },
      { label: 'Домены регистрации', path: '/admin/email-domains', icon: 'mail' },
      { label: 'Журнал действий',    path: '/admin/audit',         icon: 'file' },
    ],
  },
  {
    label: 'Аккаунт',
    items: [
      { label: 'Безопасность', path: '/admin/settings', icon: 'settings' },
    ],
  },
];

// Единый источник истины для sidebar-ссылок и breadcrumb-подписей — исключает
// рассинхронизацию label между ними.
const CRUMB_LABELS = ADMIN_NAV_GROUPS.reduce((acc, group) => {
  group.items.forEach(({ path, label }) => { acc[path] = label; });
  return acc;
}, {});

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
    <div className={styles.app} data-cabinet-shell>
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
          {ADMIN_NAV_GROUPS.map((group) => (
            <div key={group.label} className={styles.navGroup}>
              <div className={styles.navSectionLabel}>{group.label}</div>
              {group.items.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    `${styles.navItem} ${isActive ? styles.active : ''}`
                  }
                  aria-label={item.label}
                  title={item.label}
                >
                  <span className={styles.navIcon}>
                    <Icon name={item.icon} size={18} />
                  </span>
                  <span className={styles.navLabel}>{item.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className={styles.foot}>
          ФГАОУ ВО «Донецкий государственный университет»
          <br />
          <a href="mailto:support@donnu.ru">support@donnu.ru</a>
        </div>

      </aside>

      <main className={styles.main} data-cabinet-main>
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
            <A11yToggle compact />
            <ThemeToggle compact />
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

        {/* Панель настроек ГОСТ — под шапкой, видна только в режиме */}
        <A11yPanel />

        <div className={styles.content} data-cabinet-content>
          <div className={styles.contentInner}>
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
}
