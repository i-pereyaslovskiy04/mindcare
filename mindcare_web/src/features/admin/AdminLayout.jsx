import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useLocation, Outlet, NavLink, Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import CabinetSwitcher from '../auth/CabinetSwitcher';
import Icon from '../../components/Icon/Icon';
import CabinetHeader from '../../components/CabinetHeader/CabinetHeader';
import CabinetDrawer from '../../components/CabinetDrawer/CabinetDrawer';
import { resolveBreadcrumbs } from '../../components/CabinetHeader/breadcrumbs';
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
      { label: 'Карточки услуг', path: '/admin/service-cards', icon: 'image' },
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

const DYNAMIC_CRUMBS = [
  { prefix: '/admin/tests/', label: 'Тест', parent: '/admin/tests' },
];

// Корень админки: index-маршрут /admin перенаправляет на /admin/users.
const ADMIN_HOME = '/admin';

export default function AdminLayout() {
  const { pathname } = useLocation();
  const { user, activeRole, setActiveRole } = useAuth();
  const breadcrumbs = resolveBreadcrumbs({
    pathname,
    homePath: ADMIN_HOME,
    crumbLabels: CRUMB_LABELS,
    dynamicCrumbs: DYNAMIC_CRUMBS,
  });

  // Синхронизируем activeRole с открытым admin-кабинетом (прямой URL/reload).
  useEffect(() => {
    if (activeRole !== 'admin' && normalizeRoles(user).includes('admin')) {
      setActiveRole('admin');
    }
  }, [activeRole, user, setActiveRole]);

  // Мобильное меню (drawer, <=600px) — та же модель, что в CabinetLayout.
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  const menuButtonRef = useRef(null);
  const drawerId = useId();

  // Закрывать drawer при переходе в другой раздел.
  useEffect(() => { setMenuOpen(false); }, [pathname]);

  // Разметка sidebar переиспользуется в desktop aside и в mobile drawer —
  // навигация одна (ADMIN_NAV_GROUPS), отдельной мобильной копии нет.
  const sidebarInner = (
    <>
      {/* Текстовый brand — ссылка на главную панели управления. */}
      <Link
        to={ADMIN_HOME}
        className={styles.brand}
        aria-label="Психология ДонГУ, панель управления — на главную"
        title="На главную панели управления"
        onClick={closeMenu}
      >
        {/* Монограмма icon-rail (<=980px): «ПД» — Психология ДонГУ. */}
        <span className={styles.brandShort} aria-hidden="true">ПД</span>
        <span className={styles.brandFull}>
          Психо<em>логия</em> ДонГУ
        </span>
        <span className={styles.brandSub}>Панель управления</span>
      </Link>

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
                onClick={closeMenu}
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
    </>
  );

  return (
    <div className={styles.app} data-cabinet-shell>
      {/* Sidebar: полный >980px, icon-rail 601–980px, скрыт <=600px. */}
      <aside className={styles.sidebar}>{sidebarInner}</aside>

      <main className={styles.main} data-cabinet-main>
        <CabinetHeader
          className={styles.topbar}
          cabinetRole="admin"
          breadcrumbs={breadcrumbs}
          onMenuOpen={() => setMenuOpen(true)}
          menuOpen={menuOpen}
          menuId={drawerId}
          menuButtonRef={menuButtonRef}
        />

        {/* Панель настроек ГОСТ — под шапкой, видна только в режиме */}
        <A11yPanel />

        <div className={styles.content} data-cabinet-content>
          <div className={styles.contentInner}>
            <Outlet />
          </div>
        </div>
      </main>

      {/* Mobile drawer (<=600px, only when open). */}
      <CabinetDrawer
        open={menuOpen}
        onClose={closeMenu}
        returnFocusRef={menuButtonRef}
        id={drawerId}
        label="Меню панели управления"
        className={styles.mobileDrawer}
      >
        {sidebarInner}
      </CabinetDrawer>
    </div>
  );
}
