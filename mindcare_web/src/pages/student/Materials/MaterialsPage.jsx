import { useState } from 'react';
import Icon from '../components/Icon';
import styles from './MaterialsPage.module.css';

const TOPICS = ['Все', 'Тревога', 'Стресс', 'Сон', 'Отношения', 'Самооценка', 'Эмоции'];

const ARTICLES = [
  { id: 1,  title: 'Когда тревога говорит правду — а когда обманывает', topic: 'Тревога',    date: '24 апр', time: '7 мин'  },
  { id: 2,  title: 'Почему мы просыпаемся в 4 утра. Спокойный взгляд',  topic: 'Сон',       date: '21 апр', time: '5 мин'  },
  { id: 3,  title: 'Дыхание 4-7-8: короткая практика на каждый день',    topic: 'Стресс',    date: '19 апр', time: '3 мин'  },
  { id: 4,  title: 'Как просить о поддержке, когда не умеешь',           topic: 'Отношения', date: '15 апр', time: '9 мин'  },
  { id: 5,  title: 'Гнев как сигнал, а не враг',                         topic: 'Эмоции',    date: '12 апр', time: '6 мин'  },
  { id: 6,  title: 'Внутренний критик: научиться разговаривать иначе',   topic: 'Самооценка',date: '8 апр',  time: '8 мин'  },
  { id: 7,  title: 'Гигиена сна: что действительно работает',            topic: 'Сон',       date: '4 апр',  time: '5 мин'  },
  { id: 8,  title: 'Заземление 5-4-3-2-1: вернуться в настоящее',        topic: 'Тревога',   date: '1 апр',  time: '2 мин'  },
  { id: 9,  title: 'Стресс и тело: как напряжение живёт в нас',          topic: 'Стресс',    date: '28 мар', time: '6 мин'  },
  { id: 10, title: 'Самосострадание: относиться к себе по-другому',      topic: 'Самооценка',date: '24 мар', time: '7 мин'  },
  { id: 11, title: 'Эмоциональные границы в близких отношениях',         topic: 'Отношения', date: '20 мар', time: '10 мин' },
  { id: 12, title: 'Дневник эмоций: зачем и как вести',                  topic: 'Эмоции',    date: '16 мар', time: '5 мин'  },
];

const PAGE_SIZE = 8;

export default function MaterialsPage() {
  const [topic, setTopic]       = useState('Все');
  const [favs, setFavs]         = useState([2, 5]);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  function toggleFav(id, e) {
    e.stopPropagation();
    setFavs((prev) =>
      prev.includes(id) ? prev.filter((f) => f !== id) : [...prev, id]
    );
  }

  function handleTopicChange(t) {
    setTopic(t);
    setVisibleCount(PAGE_SIZE);
  }

  const filtered = ARTICLES.filter((a) => topic === 'Все' || a.topic === topic);
  const visible  = filtered.slice(0, visibleCount);
  const hasMore  = visibleCount < filtered.length;

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>
        Материалы <em>и статьи</em>
      </h1>
      <p className={styles.pageSub}>
        Подобранные специалистами тексты, аудиопрактики и упражнения. Сохраняйте важное в избранное.
      </p>

      <div className={styles.topicFilters}>
        {TOPICS.map((t) => (
          <button
            key={t}
            className={`${styles.chip} ${topic === t ? styles.chipActive : ''}`}
            onClick={() => handleTopicChange(t)}
          >
            {t}
          </button>
        ))}
        <div className={styles.chipSpacer} />
        <button className={styles.chip}>
          <Icon name="heart" size={12} />
          Избранное · {favs.length}
        </button>
      </div>

      <div className={`${styles.grid} ${styles.g4}`}>
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
          <button
            className={styles.loadMoreBtn}
            onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
          >
            Загрузить ещё
          </button>
        </div>
      )}
    </div>
  );
}
