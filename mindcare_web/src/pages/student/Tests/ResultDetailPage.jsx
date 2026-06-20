import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Icon from '../../../components/Icon/Icon';
import Button from '../../../components/UI/Button/Button';
import { getTestResult } from '../../../api/tests.api';
import styles from './ResultDetailPage.module.css';

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

function pct(score, max) {
  if (score == null || !max) return null;
  return Math.round((score / max) * 100);
}

export default function ResultDetailPage() {
  const { uuid } = useParams();
  const navigate = useNavigate();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getTestResult(uuid)
      .then((r) => { if (alive) setResult(r); })
      .catch((err) => { if (alive) setError(err.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [uuid]);

  if (loading) return <div className={styles.page}><p className={styles.muted}>Загрузка…</p></div>;

  if (error || !result) {
    return (
      <div className={styles.page}>
        <button className={styles.back} type="button" onClick={() => navigate('/student/tests/results')}>
          <Icon name="chevron-left" size={14} /> К результатам
        </button>
        <p className={styles.error}>{error || 'Результат не найден'}</p>
      </div>
    );
  }

  const overallPct = pct(result.total_score, result.max_possible);

  return (
    <div className={styles.page}>
      <button className={styles.back} type="button" onClick={() => navigate('/student/tests/results')}>
        <Icon name="chevron-left" size={14} /> К результатам
      </button>

      <div className={styles.labelTag}>Результат теста</div>
      <h1 className={styles.pageTitle}>{result.test_title || 'Тест'}</h1>
      <p className={styles.date}>Пройден {formatDate(result.submitted_at)}</p>

      {/* Итоговый балл — для одношкальных тестов */}
      {result.total_score != null && (
        <div className={styles.scoreCard}>
          <div className={styles.scoreHead}>
            <span className={styles.scoreLabel}>Итоговый балл</span>
            <span className={styles.scoreValue}>
              {result.total_score}
              {result.max_possible != null && (
                <span className={styles.scoreMax}> / {result.max_possible}</span>
              )}
            </span>
          </div>
          {overallPct != null && (
            <div className={styles.pbar}>
              <div className={styles.pbarFill} style={{ width: `${overallPct}%` }} />
            </div>
          )}
          {result.recommendations && (
            <p className={styles.recommend}>{result.recommendations}</p>
          )}
        </div>
      )}

      {/* Результаты по шкалам — для многошкальных тестов */}
      {result.scales?.length > 0 && (
        <div className={styles.scales}>
          <h2 className={styles.hSection}>Результаты по шкалам</h2>
          {result.scales.map((s) => {
            const sp = pct(s.score, s.max_score);
            return (
              <div key={s.scale_name} className={styles.scaleCard}>
                <div className={styles.scaleHead}>
                  <span className={styles.scaleName}>{s.scale_name}</span>
                  <span className={styles.scaleScore}>
                    {s.score}
                    {s.max_score != null && <span className={styles.scoreMax}> / {s.max_score}</span>}
                  </span>
                </div>
                {sp != null && (
                  <div className={styles.pbar}>
                    <div className={styles.pbarFill} style={{ width: `${sp}%` }} />
                  </div>
                )}
                {s.label && <div className={styles.scaleTag}>{s.label}</div>}
                {s.interpretation && <p className={styles.recommend}>{s.interpretation}</p>}
              </div>
            );
          })}
        </div>
      )}

      <div className={styles.actions}>
        <Button variant="secondary" onClick={() => navigate('/student/tests/catalog')}>
          Пройти другой тест
        </Button>
      </div>
    </div>
  );
}
