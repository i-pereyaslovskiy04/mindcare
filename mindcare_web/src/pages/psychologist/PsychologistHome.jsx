import { useAuth } from '../../features/auth/AuthContext';
import styles from '../../components/CabinetLayout/CabinetHome.module.css';

function getFirstName(fullName) {
  if (!fullName) return '';
  return fullName.trim().split(/\s+/)[0];
}

export default function PsychologistHome() {
  const { user } = useAuth();
  const today    = new Date().toLocaleDateString('ru-RU', {
    weekday: 'long', day: 'numeric', month: 'long',
  });

  return (
    <div className={styles.page}>
      <div className={styles.labelTag}>{today}</div>
      <h1 className={styles.pageTitle}>
        Здравствуйте, <em>{getFirstName(user?.name)}</em>
      </h1>
      <p className={styles.pageSub}>
        Добро пожаловать в кабинет психолога. Раздел активно развивается.
      </p>

      {/* Welcome + hint */}
      <div className={`${styles.grid} ${styles.g21}`} style={{ marginBottom: 16 }}>
        <div className={styles.darkCard}>
          <div className={styles.darkCardTitle}>
            Ваш рабочий<br /><em>кабинет</em>
          </div>
          <div className={styles.darkCardSub}>
            Здесь будут ваши клиенты, сессии и рабочие материалы.
            Раздел находится в активной разработке.
          </div>
          <div className={styles.darkCardBtns}>
            <button type="button" className={`${styles.btn} ${styles.btnLatte}`}>
              Настройки профиля
            </button>
          </div>
        </div>

        <div className={styles.card} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className={styles.sectionTitle}>Сегодня</div>
          <div className={styles.liRow}>
            <div className={styles.liIcon}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="4" width="18" height="18" rx="2" />
                <path d="M16 2v4M8 2v4M3 10h18" />
              </svg>
            </div>
            <div className={styles.liBody}>
              <div className={styles.liTitle}>Сессий запланировано</div>
              <div className={styles.liDesc}>Расписание недоступно</div>
            </div>
            <span className={styles.liBadge}>скоро</span>
          </div>
          <div className={styles.liRow}>
            <div className={styles.liIcon}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>
            <div className={styles.liBody}>
              <div className={styles.liTitle}>Активных клиентов</div>
              <div className={styles.liDesc}>База клиентов недоступна</div>
            </div>
            <span className={styles.liBadge}>скоро</span>
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div className={`${styles.grid} ${styles.g3}`} style={{ marginBottom: 16 }}>
        <div className={styles.statCard}>
          <div className={styles.statLabel}>Сессий за месяц</div>
          <div className={styles.statValue}>—</div>
          <div className={styles.statDesc}>Данные будут доступны позже</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statLabel}>Клиентов</div>
          <div className={styles.statValue}>—</div>
          <div className={styles.statDesc}>Данные будут доступны позже</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statLabel}>Непрочитанных</div>
          <div className={styles.statValue}>—</div>
          <div className={styles.statDesc}>Сообщения недоступны</div>
        </div>
      </div>

      {/* Coming soon */}
      <div className={styles.noticeCard}>
        <div className={styles.noticeTitle}>Раздел находится в разработке</div>
        <div className={styles.noticeText}>
          Кабинет психолога скоро получит полный функционал: управление клиентами,
          ведение сессий, рабочие материалы и статистику.
        </div>
      </div>
    </div>
  );
}
