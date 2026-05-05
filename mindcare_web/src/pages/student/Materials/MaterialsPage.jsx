import Icon from '../components/Icon';
import SearchBar from '../../materials/components/SearchBar';
import { useStudentMaterials } from './useStudentMaterials';
import { TAG_OPTIONS, TOPIC_OPTIONS } from '../../../hooks/useMaterials';
import styles from './MaterialsPage.module.css';

export default function MaterialsPage() {
  const {
    setQuery,
    selectedTags,   setSelectedTags,
    selectedTopics, setSelectedTopics,
    sort, setSort,
    favs, toggleFav,
    showFavsOnly, setShowFavsOnly,
    visible, hasMore, loadMore,
  } = useStudentMaterials();

  return (
    <div className={styles.page}>
      <div className={styles.labelTag}>Библиотека</div>
      <h1 className={styles.pageTitle}>
        Материалы <em>и статьи</em>
      </h1>
      <p className={styles.pageSub}>
        Подобранные специалистами тексты, аудиопрактики и упражнения. Сохраняйте важное в избранное.
      </p>

      <SearchBar
        onQueryChange={setQuery}
        selectedTags={selectedTags}
        onTagsChange={setSelectedTags}
        selectedTopics={selectedTopics}
        onTopicsChange={setSelectedTopics}
        sort={sort}
        onSortChange={setSort}
        tagOptions={TAG_OPTIONS}
        topicOptions={TOPIC_OPTIONS}
      />

      <div className={styles.favsRow}>
        <button
          className={`${styles.chip} ${showFavsOnly ? styles.chipActive : ''}`}
          onClick={() => setShowFavsOnly((v) => !v)}
        >
          <Icon name="heart" size={12} />
          Избранное · {favs.length}
        </button>
      </div>

      <div className={`${styles.grid} ${styles.g4}`}>
        {visible.length === 0 && (
          <p className={styles.emptyState}>Ничего не найдено — попробуйте изменить фильтры.</p>
        )}
        {visible.map((article) => {
          const liked = favs.includes(article.id);
          return (
            <div key={article.id} className={styles.articleCard}>
              <div className={styles.articleImg}>
                <Icon name="articles" size={36} />
                <button
                  className={`${styles.articleFav} ${liked ? styles.articleFavOn : ''}`}
                  onClick={(e) => toggleFav(article.id, e)}
                  aria-label={liked ? 'Убрать из избранного' : 'Добавить в избранное'}
                >
                  <Icon name={liked ? 'heart' : 'heart-o'} size={14} />
                </button>
              </div>
              <div className={styles.articleBody}>
                <span className={styles.articleTopic}>{article.topic}</span>
                <div className={styles.articleTitle}>{article.title}</div>
                <div className={styles.articleMeta}>
                  <span>{article.date}</span>
                  <span>{article.time}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {hasMore && (
        <div className={styles.loadMoreWrap}>
          <button className={styles.loadMoreBtn} onClick={loadMore}>
            Загрузить ещё
          </button>
        </div>
      )}
    </div>
  );
}
