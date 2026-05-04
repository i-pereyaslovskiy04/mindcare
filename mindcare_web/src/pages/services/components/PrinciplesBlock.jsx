import styles from './PrinciplesBlock.module.css';

const LockIcon = () => (
  <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <rect x="3" y="10" width="16" height="11" rx="3" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="11" cy="15.5" r="1.5" fill="currentColor" />
  </svg>
);

const HandIcon = () => (
  <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M8 11V6a1.5 1.5 0 0 1 3 0v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M11 10V5a1.5 1.5 0 0 1 3 0v5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M14 10.5V7a1.5 1.5 0 0 1 3 0v6c0 3.5-2.5 6-6 6H9c-3 0-4.5-2-4.5-4V12l1.5-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M6 9V6a1.5 1.5 0 0 1 2 0v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const BadgeIcon = () => (
  <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <circle cx="11" cy="9" r="5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M6.5 13.5L4 20l7-3 7 3-2.5-6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M9 9l1.5 1.5L13 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const ShieldIcon = () => (
  <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M11 2L3 6v5c0 5 8 9 8 9s8-4 8-9V6L11 2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M8 11l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const HeartIcon = () => (
  <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M11 19S3 14 3 8.5A4.5 4.5 0 0 1 11 6a4.5 4.5 0 0 1 8 2.5C19 14 11 19 11 19z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </svg>
);

const PRINCIPLES = [
  { title: 'Конфиденциальность',         icon: <LockIcon /> },
  { title: 'Добровольность',             icon: <HandIcon /> },
  { title: 'Компетентность',             icon: <BadgeIcon /> },
  { title: 'Ответственность',            icon: <ShieldIcon /> },
  { title: 'Благополучие клиента',       icon: <HeartIcon /> },
];

export default function PrinciplesBlock() {
  return (
    <>
      <h2 className={styles.title}>Принципы работы</h2>
      <div className={styles.grid}>
        {PRINCIPLES.map((p) => (
          <div key={p.title} className={styles.card}>
            <div className={styles.iconWrap}>{p.icon}</div>
            <p className={styles.cardTitle}>{p.title}</p>
          </div>
        ))}
      </div>
    </>
  );
}
