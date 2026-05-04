import { useState } from 'react';
import Icon from '../components/Icon';
import styles from './MaterialsPage.module.css';

const TOPICS = ['Все', 'Тревога', 'Стресс', 'Сон', 'Отношения', 'Самооценка', 'Эмоции'];

const ARTICLES = [
  { id: 1, title: 'Как справляться с тревогой', topic: 'Тревога',    date: '28 апр', time: '8 мин'  },
  { id: 2, title: 'Гигиена сна',                  topic: 'Сон',       date: '25 апр', time: '5 мин'  },
  { id: 3, title: 'Дыхательные практики',          topic: 'Стресс',    date: '22 апр', time: '4 мин'  },
  { id: 4, title: 'Основы КПТ',                    topic: 'Самооценка',date: '19 апр', time: '12 мин' },
  { id: 5, title: 'Эмоциональный интеллект',       topic: 'Эмоции',    date: '15 апр', time: '7 мин'  },
  { id: 6, title: 'Границы в отношениях',          topic: 'Отношения', date: '10 апр', time: '10 мин' },
  { id: 7, title: 'Работа с самооценкой',          topic: 'Самооценка',date: '5 апр',  time: '6 мин'  },
  { id: 8, title: 'Антистресс-практики',           topic: 'Стресс',    date: '1 апр',  time: '5 мин'  },
];

function formatTodayLabel() {
  return new Date().toLocaleDateString('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

export default function MaterialsPage() {
  const [topic, setTopic] = useState('Все');
  const [favs, setFavs] = useState([2, 5]);

  function toggleFav(id, e) {
    e.stopPropagation();
    setFavs((prev) =>
      prev.includes(id) ? prev.filter((f) => f !== id) : [...prev, id]
    );
  }

  const visible = ARTICLES.filter((a) => topic === 'Все' || a.topic === topic);

  return (
    <div className={styles.page}>
      <div className={styles.labelTag}>{formatTodayLabel()}</div>
      <h1 className={styles.pageTitle}>
        Материалы <em>и статьи</em>
      </h1>
      <p className={styles.pageSub}>
        Полезные материалы, упражнения и статьи, подобранные вашим психологом
        и командой центра.
      </p>

      <div className={styles.topicFilters}>
        {TOPICS.map((t) => (
          <button
            key={t}
            className={`${styles.chip} ${topic === t ? styles.chipActive : ''}`}
            onClick={() => setTopic(t)}
          >
            {t}
          </button>
        ))}
        <button className={`${styles.chip} ${styles.chipFav}`}>
          <Icon name="heart" size={12} />
          {favs.length}
        </button>
      </div>

      <div className={`${styles.grid} ${styles.g4}`}>
        {visible.map((article) => (
          <div key={article.id} className={styles.articleCard}>
            <div className={styles.articleImg}>
              <Icon name="articles" size={32} />
              <button
                className={`${styles.articleFav} ${
                  favs.includes(article.id) ? styles.articleFavOn : ''
                }`}
                onClick={(e) => toggleFav(article.id, e)}
                aria-label="Добавить в избранное"
              >
                <Icon name="heart" size={14} />
              </button>
            </div>
            <div className={styles.articleBody}>
              <div className={styles.articleTopic}>{article.topic}</div>
              <div className={styles.articleTitle}>{article.title}</div>
              <div className={styles.articleMeta}>
                <span>{article.date}</span>
                <span>{article.time} чтения</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
