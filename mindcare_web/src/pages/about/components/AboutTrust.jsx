import styles from './AboutTrust.module.css';

const LockIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="9" width="14" height="10" rx="3" stroke="currentColor" strokeWidth="1.5" />
    <path d="M6 9V7a4 4 0 0 1 8 0v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="10" cy="14" r="1.5" fill="currentColor" />
  </svg>
);

const EyeOffIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M2 10s3-6 8-6 8 6 8 6-3 6-8 6-8-6-8-6z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5" />
    <line x1="3" y1="3" x2="17" y2="17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const BadgeIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="8" r="4.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M6 12.5L4 18l6-2.5 6 2.5-2-5.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M8 8l1.5 1.5L12 6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const GUARANTEES = [
  {
    icon: <LockIcon />,
    title: 'Конфиденциальность',
    desc: 'Всё, что обсуждается на сессии, остаётся между вами и специалистом.',
  },
  {
    icon: <EyeOffIcon />,
    title: 'Анонимность',
    desc: 'Возможность обратиться без указания личных данных.',
  },
  {
    icon: <BadgeIcon />,
    title: 'Профессионализм',
    desc: 'Все специалисты имеют профильное образование и регулярно повышают квалификацию.',
  },
];

export default function AboutTrust() {
  return (
    <section className="section-wrap">
      <div className="container">
        <h2 className={styles.title}>Доверие и безопасность</h2>
        <div className={styles.cards}>
          {GUARANTEES.map((g) => (
            <div key={g.title} className={styles.card}>
              <div className={styles.iconWrap}>{g.icon}</div>
              <h3 className={styles.cardTitle}>{g.title}</h3>
              <p className={styles.cardDesc}>{g.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
