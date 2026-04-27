import styles from './QuickActions.module.css';

const CalendarIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="1.5" y="2.5" width="17" height="15" rx="2.5" stroke="#8B6F47" strokeWidth="1.4" fill="none" />
    <path d="M5.5 1v3M14.5 1v3M1.5 9h17" stroke="#8B6F47" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

const StarIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path
      d="M10 2l1.9 3.8 4.2.6-3 2.9.7 4.2-3.8-2-3.8 2 .7-4.2-3-2.9 4.2-.6L10 2z"
      stroke="#8B6F47"
      strokeWidth="1.4"
      fill="none"
      strokeLinejoin="round"
    />
  </svg>
);

const UserIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="7" r="4.5" stroke="#8B6F47" strokeWidth="1.4" fill="none" />
    <path d="M2 19c0-4.418 3.582-8 8-8s8 3.582 8 8" stroke="#8B6F47" strokeWidth="1.4" fill="none" />
  </svg>
);

const ACTIONS = [
  {
    id: 'booking',
    Icon: CalendarIcon,
    title: 'Записаться',
    subtitle: 'Выбрать психолога и время',
  },
  {
    id: 'diagnostics',
    Icon: StarIcon,
    title: 'Психодиагностика',
    subtitle: 'Тесты и самопознание',
  },
  {
    id: 'profile',
    Icon: UserIcon,
    title: 'Личный кабинет',
    subtitle: 'Войти или зарегистрироваться',
  },
];

export default function QuickActions({ onOpenAuth }) {
  const getClickHandler = (id) => {
    if (id === 'profile') return onOpenAuth;
    return undefined; // booking/diagnostics not yet implemented
  };

  return (
    <div className={styles.quickActions}>
      <div className={`container ${styles.quickActionsContainer}`}>
        <div className={styles.qaGrid}>
          {ACTIONS.map(({ id, Icon, title, subtitle }) => (
            <button
              key={id}
              className={styles.qaItem}
              onClick={getClickHandler(id)}
              aria-label={`${title}: ${subtitle}`}
              type="button"
            >
              <div className={styles.qaIcon}>
                <Icon />
              </div>
              <div>
                <div className={styles.qaTextTitle}>{title}</div>
                <div className={styles.qaTextSub}>{subtitle}</div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
