import { useNavigate } from 'react-router-dom';
import Icon from '../../../components/Icon/Icon';
import Tag from '../../../components/UI/Tag/Tag';
import Button from '../../../components/UI/Button/Button';
import { useTestCatalog } from './hooks/useTestCatalog';
import styles from './TestCatalogPage.module.css';

function questionLabel(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} вопрос`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return `${n} вопроса`;
  return `${n} вопросов`;
}

export default function TestCatalogPage() {
  const navigate = useNavigate();
  const { items, total, loading, error, query, setQuery, hasMore, loadMore } = useTestCatalog();

  return (
    <div className={styles.page}>
      <button className={styles.back} type="button" onClick={() => navigate('/student/tests')}>
        <Icon name="chevron-left" size={14} />
        К результатам
      </button>

      <div className={styles.labelTag}>Каталог методик</div>
      <h1 className={styles.pageTitle}>
        Доступные <em>тесты</em>
      </h1>
      <p className={styles.pageSub}>
        Подобранные специалистами методики самодиагностики. Выберите тест, чтобы пройти его.
      </p>

      <div className={styles.searchRow}>
        <Icon name="search" size={15} className={styles.searchIcon} />
        <input
          className={styles.search}
          type="search"
          value={query}
          placeholder="Поиск по названию…"
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {!loading && !error && items.length === 0 && (
        <p className={styles.empty}>Пока нет доступных тестов.</p>
      )}

      <div className={styles.grid}>
        {items.map((t) => (
          <div key={t.uuid} className={styles.card}>
            <div className={styles.cardBody}>
              <h3 className={styles.hCard}>{t.title}</h3>
              {t.description && <p className={styles.cardDesc}>{t.description}</p>}
              <div className={styles.metaRow}>
                <span className={styles.meta}>{questionLabel(t.question_count)}</span>
                {t.time_limit_min ? (
                  <span className={styles.meta}>· ≈ {t.time_limit_min} мин</span>
                ) : null}
              </div>
              {t.tags?.length > 0 && (
                <div className={styles.tags}>
                  {t.tags.map((tag) => (
                    <Tag key={tag.uuid}>{tag.name}</Tag>
                  ))}
                </div>
              )}
            </div>
            <Button
              variant="primary"
              className={styles.takeBtn}
              onClick={() => navigate(`/student/tests/catalog/${t.uuid}`)}
            >
              Пройти тест <Icon name="arrow-right" size={13} />
            </Button>
          </div>
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
