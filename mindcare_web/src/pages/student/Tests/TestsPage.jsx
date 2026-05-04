import Icon from '../components/Icon';
import styles from './TestsPage.module.css';

const RESULTS = [
  {
    id: 1,
    name: 'Колесо баланса',
    full: 'Самопознание · 8 сфер жизни',
    date: '12 апреля',
    score: '7.2 / 10',
    summary: 'Опора — отдых и развитие. Внимание — отношения и тело.',
    pct: 72,
  },
  {
    id: 2,
    name: 'WEMWBS',
    full: 'Шкала ментального благополучия',
    date: '5 апреля',
    score: '51 / 70',
    summary: 'Благополучие в пределах нормы — стабильное состояние.',
    pct: 73,
  },
  {
    id: 3,
    name: 'GAD-7',
    full: 'Шкала генерализованной тревоги',
    date: '29 марта',
    score: '11 / 21',
    summary: 'Умеренная тревога. Снижение по сравнению с прошлым месяцем.',
    pct: 52,
  },
  {
    id: 4,
    name: 'PHQ-9',
    full: 'Шкала депрессии',
    date: '22 марта',
    score: '8 / 27',
    summary: 'Мягкие признаки сниженного настроения. Без уточняющих рекомендаций.',
    pct: 30,
  },
];

export default function TestsPage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>
        Тесты и <em>самопознание</em>
      </h1>
      <p className={styles.pageSub}>
        Здесь собраны результаты пройденных вами методик. Чтобы пройти новый тест — откройте каталог.
      </p>

      <div className={styles.catalogCard}>
        <div>
          <div className={styles.labelTag}>Каталог методик</div>
          <h2 className={styles.hSection} style={{ marginTop: 4 }}>
            Все доступные тесты
          </h2>
          <div className={styles.catalogSub}>
            GAD-7, PHQ-9, PSS-10, ISI и другие — подобранные специалистами.
          </div>
        </div>
        <button className={`${styles.btn} ${styles.btnPrimary}`}>
          Все тесты <Icon name="arrow-right" size={14} />
        </button>
      </div>

      <h2 className={styles.hSection} style={{ marginBottom: 14 }}>
        Результаты пройденных тестов{' '}
        <span className={styles.sectionMeta}>· {RESULTS.length}</span>
      </h2>

      <div className={`${styles.grid} ${styles.g2}`}>
        {RESULTS.map((r) => (
          <div key={r.id} className={styles.testCard}>
            <div className={styles.testCardHead}>
              <div>
                <div className={styles.labelTag}>{r.name}</div>
                <h3 className={styles.hCard}>{r.full}</h3>
              </div>
              <span className={`${styles.badge} ${styles.badgeDone}`}>пройден</span>
            </div>
            <div className={styles.testDateRow}>
              <div className={styles.testDate}>{r.date}</div>
              <div className={styles.testScore}>{r.score}</div>
            </div>
            <div className={styles.pbar}>
              <div className={styles.pbarFill} style={{ width: `${r.pct}%` }} />
            </div>
            <p className={styles.testSummary}>{r.summary}</p>
            <button className={`${styles.btn} ${styles.btnSoft}`}>
              Смотреть результат
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
