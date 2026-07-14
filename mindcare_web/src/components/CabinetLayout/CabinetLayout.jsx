import { useEffect, useState } from 'react';
import { useLocation, Outlet, NavLink } from 'react-router-dom';
import { useAuth, useLogout } from '../../features/auth/AuthContext';
import Icon from '../Icon/Icon';
import ThemeToggle from '../../features/theme/ThemeToggle';
import A11yToggle from '../../features/a11y/A11yToggle';
import A11yPanel from '../../features/a11y/A11yPanel';
import { getInitials } from '../../shared/lib/utils';
import styles from './CabinetLayout.module.css';

const ROLE_LABELS = {
  psychologist: 'Психолог',
  supervisor:   'Супервизор',
  student:      'Пациент',
};

export default function CabinetLayout({ navSections, crumbLabels, dynamicCrumbs }) {
  const { pathname } = useLocation();
  const { user }     = useAuth();
  const logout       = useLogout();
  const crumb        = crumbLabels?.[pathname]
    ?? dynamicCrumbs?.find(({ prefix }) => pathname.startsWith(prefix))?.label
    ?? 'Личный кабинет';
  const roleLabel    = ROLE_LABELS[user?.role] ?? '';

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
      <div className={styles.brand}>
        <span className={styles.brandShort}>М</span>
        <span className={styles.brandFull}>Психо<em>логия</em> ДонГУ</span>
        <span className={styles.brandSub}>Личный кабинет</span>
      </div>

      <div className={styles.user}>
        <div className={styles.avatar}>{getInitials(user?.name)}</div>
        <div className={styles.userInfo}>
          <div className={styles.userName}>{user?.name ?? roleLabel}</div>
          <div className={styles.userRole}>
            <span className={styles.roleDot} aria-hidden="true" />
            {roleLabel}
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
        <div className={styles.topbar}>
          <div className={styles.topbarLeft}>
            <button
              className={styles.mobileMenuButton}
              type="button"
              aria-label="Открыть меню"
              onClick={() => setMenuOpen(true)}
            >
              <span aria-hidden="true">☰</span>
            </button>
            <div className={styles.crumbs}>
              Личный кабинет / <span>{crumb}</span>
            </div>
          </div>
          <div className={styles.actions}>
            <div className={styles.search}>
              <Icon name="search" size={14} />
              <input type="text" placeholder="Поиск по материалам, записям…" readOnly />
            </div>
            <A11yToggle compact />
            <ThemeToggle compact />
            <button
              className={`${styles.iconBtn} ${styles.iconBtnOptional}`}
              aria-label="Уведомления"
              type="button"
            >
              <Icon name="bell" size={16} />
              <span className={styles.dot} aria-hidden="true" />
            </button>
            <button
              className={`${styles.iconBtn} ${styles.iconBtnOptional}`}
              aria-label="Почта"
              type="button"
            >
              <Icon name="mail" size={16} />
            </button>
            <button className={styles.iconBtn} aria-label="Выйти" type="button" onClick={logout}>
              <Icon name="logout" size={16} />
            </button>
          </div>
        </div>

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
