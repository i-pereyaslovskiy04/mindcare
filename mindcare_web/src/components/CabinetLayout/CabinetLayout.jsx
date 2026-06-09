import { useLocation, Outlet, NavLink } from 'react-router-dom';
import { useAuth, useLogout } from '../../features/auth/AuthContext';
import Icon from '../Icon/Icon';
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

  return (
    <div className={styles.app}>
      {/* ── SIDEBAR ──────────────────────────────────────────────── */}
      <aside className={styles.sidebar}>
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
              <span className={styles.roleDot} />
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
      </aside>

      {/* ── MAIN ─────────────────────────────────────────────────── */}
      <main className={styles.main}>
        <div className={styles.topbar}>
          <div className={styles.crumbs}>
            Личный кабинет / <span>{crumb}</span>
          </div>
          <div className={styles.actions}>
            <div className={styles.search}>
              <Icon name="search" size={14} />
              <input type="text" placeholder="Поиск по материалам, записям…" readOnly />
            </div>
            <button className={styles.iconBtn} aria-label="Уведомления" type="button">
              <Icon name="bell" size={16} />
              <span className={styles.dot} />
            </button>
            <button className={styles.iconBtn} aria-label="Почта" type="button">
              <Icon name="mail" size={16} />
            </button>
            <button className={styles.iconBtn} aria-label="Выйти" type="button" onClick={logout}>
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
