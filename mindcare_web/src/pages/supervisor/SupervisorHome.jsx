import { useAuth } from '../../features/auth/AuthContext';
import styles from '../../components/CabinetLayout/CabinetHome.module.css';

function getFirstName(fullName) {
  if (!fullName) return '';
  return fullName.trim().split(/\s+/)[0];
}

export default function SupervisorHome() {
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
        Добро пожаловать в кабинет супервизора. Раздел активно развивается.
      </p>

      {/* Welcome + hint */}
      <div className={`${styles.grid} ${styles.g21}`} style={{ marginBottom: 16 }}>
        <div className={styles.darkCard}>
          <div className={styles.darkCardTitle}>
            Кабинет<br /><em>супервизора</em>
          </div>
          <div className={styles.darkCardSub}>
            Здесь будут инструменты для супервизии психологов, просмотра
            сессий и подготовки отчётов. Раздел находится в активной разработке.
          </div>
          <div className={styles.darkCardBtns}>
            <button type="button" className={`${styles.btn} ${styles.btnLatte}`}>
              Настройки профиля
            </button>
          </div>
        </div>

        <div className={styles.card} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className={styles.sectionTitle}>Обзор</div>
          <div className={styles.liRow}>
            <div className={styles.liIcon}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>
            <div className={styles.liBody}>
              <div className={styles.liTitle}>Психологи под наблюдением</div>
              <div className={styles.liDesc}>Список будет доступен позже</div>
            </div>
            <span className={styles.liBadge}>скоро</span>
          </div>
          <div className={styles.liRow}>
            <div className={styles.liIcon}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
            </div>
            <div className={styles.liBody}>
              <div className={styles.liTitle}>Отчёты</div>
              <div className={styles.liDesc}>Модуль отчётности в разработке</div>
            </div>
            <span className={styles.liBadge}>скоро</span>
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div className={`${styles.grid} ${styles.g3}`} style={{ marginBottom: 16 }}>
        <div className={styles.statCard}>
          <div className={styles.statLabel}>Психологов</div>
          <div className={styles.statValue}>—</div>
          <div className={styles.statDesc}>Данные будут доступны позже</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statLabel}>Сессий на проверке</div>
          <div className={styles.statValue}>—</div>
          <div className={styles.statDesc}>Данные будут доступны позже</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statLabel}>Отчётов</div>
          <div className={styles.statValue}>—</div>
          <div className={styles.statDesc}>Данные будут доступны позже</div>
        </div>
      </div>

      {/* Coming soon */}
      <div className={styles.noticeCard}>
        <div className={styles.noticeTitle}>Раздел находится в разработке</div>
        <div className={styles.noticeText}>
          Кабинет супервизора скоро получит полный функционал: список психологов,
          просмотр сессий, формирование отчётов и инструменты обратной связи.
        </div>
      </div>
    </div>
  );
}
