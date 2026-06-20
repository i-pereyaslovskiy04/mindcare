import { useNavigate } from 'react-router-dom';
import Icon from '../../../components/Icon/Icon';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import { useTestResults } from './hooks/useTestResults';
import styles from './TestsPage.module.css';

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
}

function pct(score, max) {
  if (score == null || !max) return 0;
  return Math.round((score / max) * 100);
}

export default function TestsPage() {
  const navigate = useNavigate();
  const { items, total, loading, error } = useTestResults(4);

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
            Методики самодиагностики, подобранные специалистами службы.
          </div>
        </div>
        <Button variant="primary" onClick={() => navigate('/student/tests/catalog')}>
          Все тесты <Icon name="arrow-right" size={14} />
        </Button>
      </div>

      <h2 className={styles.hSection} style={{ marginBottom: 14 }}>
        Результаты пройденных тестов
        {total > 0 && <span className={styles.sectionMeta}> · {total}</span>}
      </h2>

      {error && <p className={styles.error}>{error}</p>}

      {!loading && !error && items.length === 0 && (
        <p className={styles.empty}>
          Вы ещё не проходили тесты. Откройте каталог, чтобы начать.
        </p>
      )}

      <div className={`${styles.grid} ${styles.g2}`}>
        {items.map((r) => {
          const p = pct(r.total_score, r.max_possible);
          return (
            <div key={r.uuid} className={styles.testCard}>
              <div className={styles.testCardHead}>
                <div>
                  <h3 className={styles.hCard}>{r.test_title || 'Тест'}</h3>
                </div>
                <Badge tone="success">пройден</Badge>
              </div>
              <div className={styles.testDateRow}>
                <div className={styles.testDate}>{formatDate(r.submitted_at)}</div>
                <div className={styles.testScore}>
                  {r.total_score != null
                    ? `${r.total_score}${r.max_possible != null ? ` / ${r.max_possible}` : ''}`
                    : 'по шкалам'}
                </div>
              </div>
              {r.total_score != null && r.max_possible != null && (
                <div className={styles.pbar}>
                  <div className={styles.pbarFill} style={{ width: `${p}%` }} />
                </div>
              )}
              <div style={{ flex: 1 }} />
              <Button
                variant="secondary"
                style={{ width: '100%', marginTop: 14 }}
                onClick={() => navigate(`/student/tests/results/${r.uuid}`)}
              >
                Смотреть результат
              </Button>
            </div>
          );
        })}
      </div>

      {total > items.length && (
        <div className={styles.allResultsRow}>
          <Button variant="ghost" onClick={() => navigate('/student/tests/results')}>
            Вся история результатов <Icon name="arrow-right" size={14} />
          </Button>
        </div>
      )}
    </div>
  );
}
