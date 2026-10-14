import { useEffect, useState } from 'react';
import { useLocation, Outlet, NavLink, Link } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import CabinetSwitcher from '../../features/auth/CabinetSwitcher';
import Icon from '../Icon/Icon';
import CabinetHeader from '../CabinetHeader/CabinetHeader';
import { resolveBreadcrumbs } from '../CabinetHeader/breadcrumbs';
import A11yPanel from '../../features/a11y/A11yPanel';
import { getInitials } from '../../shared/lib/utils';
import { ROLE_LABELS, normalizeRoles } from '../../shared/lib/roles';
import styles from './CabinetLayout.module.css';

/**
 * dynamicCrumbs — [{ prefix, label, parent? }] для страниц с параметром в пути;
 * parent — путь раздела из crumbLabels (промежуточная крошка-ссылка).
 */
export default function CabinetLayout({ cabinetRole, navSections, crumbLabels, dynamicCrumbs }) {
  const { pathname } = useLocation();
  const { user, activeRole, setActiveRole } = useAuth();
  // Корень кабинета = префикс его маршрутов (/student, /psychologist, /supervisor).
  const homePath     = `/${cabinetRole}`;
  const breadcrumbs  = resolveBreadcrumbs({ pathname, homePath, crumbLabels, dynamicCrumbs });
  // Лейбл — из cabinetRole (текущего кабинета), а не из legacy user.role.
  const roleLabel    = ROLE_LABELS[cabinetRole] ?? '';

  // Синхронизируем activeRole с реально открытым кабинетом (работает и при
  // прямом URL / reload, не только по клику switcher). setState — в эффекте.
  useEffect(() => {
    if (
      cabinetRole &&
      cabinetRole !== activeRole &&
      normalizeRoles(user).includes(cabinetRole)
    ) {
      setActiveRole(cabinetRole);
    }
  }, [cabinetRole, activeRole, user, setActiveRole]);

  // Мобильное меню (drawer). На desktop кнопка скрыта, drawer не открыть.
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);

  // Закрывать drawer при переходе в другой раздел.
  useEffect(() => { setMenuOpen(false); }, [pathname]);

  // Escape закрывает drawer.
  useEffect(() => {
    if (!menuOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setMenuOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  // Разметка сайдбара переиспользуется и в desktop aside, и в mobile drawer.
  // navSections приходят по роли через props — отдельной мобильной навигации нет.
  const sidebarInner = (
    <>
      {/* Текстовый brand — ссылка на главную текущего кабинета (и монограмма
          в icon-rail, и brand в mobile drawer). */}
      <Link
        to={homePath}
        className={styles.brand}
        aria-label="Психология ДонГУ, личный кабинет — на главную"
        title="На главную кабинета"
        onClick={closeMenu}
      >
        {/* Монограмма icon-rail (<=980px): «ПД» — Психология ДонГУ. */}
        <span className={styles.brandShort} aria-hidden="true">ПД</span>
        <span className={styles.brandFull}>Психо<em>логия</em> ДонГУ</span>
        <span className={styles.brandSub}>Личный кабинет</span>
      </Link>

      <div className={styles.user}>
        <div className={styles.avatar}>{getInitials(user?.name)}</div>
        <div className={styles.userInfo}>
          <div className={styles.userName}>{user?.name ?? roleLabel}</div>
          <div className={styles.userRole}>
            <CabinetSwitcher currentRole={cabinetRole} />
          </div>
        </div>
      </div>

      <nav className={styles.nav}>
        {navSections.map(section => (
          <div key={section.label}>
            <div className={styles.navSectionLabel}>{section.label}</div>
            {section.items.map(item =>
              item.disabled ? (
                <span
                  key={item.key}
                  className={`${styles.navItem} ${styles.navItemDisabled}`}
                  title="Скоро будет доступно"
                >
                  <span className={styles.navIcon}><Icon name={item.icon} size={18} /></span>
                  <span className={styles.navLabel}>{item.label}</span>
                  <span className={styles.navBadgeSoon}>скоро</span>
                </span>
              ) : (
                <NavLink
                  key={item.key}
                  to={item.to}
                  end={item.end ?? true}
                  onClick={closeMenu}
                  className={({ isActive }) =>
                    `${styles.navItem}${isActive ? ` ${styles.active}` : ''}`
                  }
                >
                  <span className={styles.navIcon}><Icon name={item.icon} size={18} /></span>
                  <span className={styles.navLabel}>{item.label}</span>
                  {item.badge != null && <span className={styles.badge}>{item.badge}</span>}
                </NavLink>
              )
            )}
          </div>
        ))}
      </nav>

      <div className={styles.foot}>
        ФГАОУ ВО «Донецкий государственный университет»<br />
        <a href="mailto:support@donnu.ru">support@donnu.ru</a>
      </div>
    </>
  );

  return (
    <div className={styles.app} data-cabinet-shell>
      {/* ── SIDEBAR (desktop) ────────────────────────────────────── */}
      <aside className={styles.sidebar}>{sidebarInner}</aside>

      {/* ── MAIN ─────────────────────────────────────────────────── */}
      <main className={styles.main} data-cabinet-main>
        <CabinetHeader
          className={styles.topbar}
          cabinetRole={cabinetRole}
          breadcrumbs={breadcrumbs}
          leading={(
            <button
              className={styles.mobileMenuButton}
              type="button"
              aria-label="Открыть меню"
              onClick={() => setMenuOpen(true)}
            >
              <span aria-hidden="true">☰</span>
            </button>
          )}
        />

        {/* Панель настроек ГОСТ — под шапкой кабинета, видна только в режиме */}
        <A11yPanel />

        <div className={styles.content} data-cabinet-content>
          <div className={styles.contentInner}>
            <Outlet />
          </div>
        </div>
      </main>

      {/* ── MOBILE DRAWER (only when open; hidden on desktop via CSS) ─ */}
      {menuOpen && (
        <>
          <div
            className={styles.mobileBackdrop}
            onClick={closeMenu}
            aria-hidden="true"
          />
          <aside
            className={styles.mobileDrawer}
            role="dialog"
            aria-modal="true"
            aria-label="Меню кабинета"
          >
            <button
              className={styles.drawerClose}
              type="button"
              aria-label="Закрыть меню"
              onClick={closeMenu}
            >
              <span aria-hidden="true">✕</span>
            </button>
            {sidebarInner}
          </aside>
        </>
      )}
    </div>
  );
}
