import { NavLink } from 'react-router-dom';
import { useAuth } from '../../../../features/auth/AuthContext';
import Icon from '../Icon';
import styles from './Sidebar.module.css';

const NAV_SECTIONS = [
  {
    label: 'Самопомощь',
    items: [
      { key: 'home',     label: 'Главная',             icon: 'home',     to: '/student' },
      { key: 'diary',    label: 'Дневник состояния',   icon: 'diary',    to: '/student/diary' },
      { key: 'tests',    label: 'Тесты',               icon: 'tests',    to: '/student/tests' },
      { key: 'materials', label: 'Материалы и статьи', icon: 'articles', to: '/student/materials' },
    ],
  },
  {
    label: 'Терапия',
    items: [
      { key: 'tasks',    label: 'Задания психолога',   icon: 'tasks',    to: '/student/tasks',    badge: '2' },
      { key: 'chat',     label: 'Чат с психологом',    icon: 'chat',     to: '/student/chat',     badge: '1' },
      { key: 'goals',    label: 'Цели терапии',        icon: 'goals',    to: '/student/goals' },
      { key: 'calendar', label: 'Календарь и сессии',  icon: 'calendar', to: '/student/calendar' },
    ],
  },
  {
    label: 'Аккаунт',
    items: [
      { key: 'settings', label: 'Настройки', icon: 'settings', to: '/student/settings' },
    ],
  },
];

function getInitials(name) {
  if (!name) return 'А';
  const parts = name.trim().split(' ');
  return parts.length >= 2
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : parts[0][0].toUpperCase();
}

export default function Sidebar() {
  const { user } = useAuth();

  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <span className={styles.brandFull}>
          Психо<em>логия</em> ДонГУ
        </span>
        <span className={styles.brandSub}>Личный кабинет</span>
      </div>

      <div className={styles.user}>
        <div className={styles.avatar}>{getInitials(user?.name)}</div>
        <div className={styles.userInfo}>
          <div className={styles.userName}>{user?.name ?? 'Студент'}</div>
          <div className={styles.userRole}>
            <span className={styles.roleDot} />
            Пациент
          </div>
        </div>
      </div>

      <nav className={styles.nav}>
        {NAV_SECTIONS.map((section) => (
          <div key={section.label}>
            <div className={styles.navSectionLabel}>{section.label}</div>
            {section.items.map((item) => (
              <NavLink
                key={item.key}
                to={item.to}
                end={item.to === '/student'}
                className={({ isActive }) =>
                  `${styles.navItem} ${isActive ? styles.active : ''}`
                }
              >
                <span className={styles.navIcon}>
                  <Icon name={item.icon} size={18} />
                </span>
                <span>{item.label}</span>
                {item.badge && (
                  <span className={styles.badge}>{item.badge}</span>
                )}
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
  );
}
