import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import styles from './NewsSection.module.css';
import FeaturedNews from './FeaturedNews';
import NewsCardSmall from './NewsCardSmall';
import NewsListItem from './NewsListItem';
import { getNews } from '../../services/api';

export default function NewsSection() {
  const [news, setNews] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getNews(1, 6).then((data) => {
      const items = Array.isArray(data) ? data : (data.items || []);
      setNews(items.slice(0, 6));
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (loading || !news.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add(styles.visible);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 }
    );

    document
      .querySelectorAll(`.${styles.newsAnimate}`)
      .forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, [news, loading]);

  const featured = news[0];
  const smallCards = news.slice(1, 3);
  const listItems = news.slice(3, 6);

  return (
    <div className="section-wrap alt">
      <div className="container">
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Новости и события</h2>
          <Link to="/news" className={styles.sectionLink}>
            Все новости →
          </Link>
        </div>

        {!loading && featured && (
          <>
            <div className={styles.newsGrid}>
              <FeaturedNews
                news={featured}
                className={styles.newsAnimate}
                style={{ animationDelay: '0s' }}
              />
              <div className={styles.newsCol}>
                {smallCards.map((card, i) => (
                  <NewsCardSmall
                    key={card.id}
                    news={card}
                    className={styles.newsAnimate}
                    style={{ animationDelay: `${0.07 + i * 0.06}s` }}
                  />
                ))}
              </div>
            </div>

            {listItems.length > 0 && (
              <div className={styles.newsList}>
                {listItems.map((item, i) => (
                  <NewsListItem
                    key={item.id}
                    news={item}
                    className={styles.newsAnimate}
                    style={{ animationDelay: `${0.18 + i * 0.06}s` }}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
