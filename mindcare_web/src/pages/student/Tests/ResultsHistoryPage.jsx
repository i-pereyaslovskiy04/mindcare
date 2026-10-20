import { useNavigate } from 'react-router-dom';
import Icon from '../../../components/Icon/Icon';
import Button from '../../../components/UI/Button/Button';
import { useTestResults } from './hooks/useTestResults';
import styles from './ResultsHistoryPage.module.css';

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

export default function ResultsHistoryPage() {
  const navigate = useNavigate();
  const { items, total, loading, error, hasMore, loadMore } = useTestResults();

  return (
    <div className={styles.page}>
      <button className={styles.back} type="button" onClick={() => navigate('/student/tests')}>
        <Icon name="chevron-left" size={14} /> Назад
      </button>

      <div className={styles.labelTag}>История</div>
      <h1 className={styles.pageTitle}>
        Пройденные <em>тесты</em>
      </h1>

      {error && <p className={styles.error}>{error}</p>}
      {!loading && !error && items.length === 0 && (
        <p className={styles.empty}>Вы ещё не проходили тесты.</p>
      )}

      <div className={styles.list}>
        {items.map((r) => (
          <button
            key={r.uuid}
            type="button"
            className={styles.row}
            onClick={() => navigate(`/student/tests/results/${r.uuid}`)}
          >
            <div className={styles.rowMain}>
              <span className={styles.rowTitle}>{r.test_title || 'Тест'}</span>
              <span className={styles.rowDate}>{formatDate(r.submitted_at)}</span>
            </div>
            <span className={styles.rowScore}>
              {r.total_score != null
                ? `${r.total_score}${r.max_possible != null ? ` / ${r.max_possible}` : ''}`
                : 'по шкалам'}
            </span>
            <Icon name="chevron-right" size={16} className={styles.rowArrow} />
          </button>
        ))}
      </div>

      {hasMore && (
        <div className={styles.moreRow}>
          <Button variant="secondary" loading={loading} onClick={loadMore}>
            Показать ещё ({items.length} из {total})
          </Button>
        </div>
      )}
    </div>
  );
}
