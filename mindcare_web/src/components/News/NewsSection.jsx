import { useEffect } from 'react';
import styles from './NewsSection.module.css';
import FeaturedNews from './FeaturedNews';
import NewsCardSmall from './NewsCardSmall';
import NewsListItem from './NewsListItem';

// Static mock data. Replace with useEffect + getNews() when API is ready.
const featuredNews = {
  id: 'open-day',
  href: '/news/open-day',
  tag: 'Мероприятия',
  title: 'Открытый день психологической службы ДонГУ',
  description: 'Приглашаем познакомиться с командой и узнать о доступных программах поддержки.',
  date: '18 апреля 2025',
};

const smallCards = [
  {
    id: 'stress',
    href: '/news/stress',
    tag: 'Статья',
    title: 'Как справляться с учебным стрессом',
    date: '14 апреля 2025',
    delay: '0.07s',
  },
  {
    id: 'anxiety-webinar',
    href: '/news/anxiety-webinar',
    tag: 'Вебинар',
    title: 'Тревожность: практика осознанности',
    date: '9 апреля 2025',
    delay: '0.13s',
  },
];

const listItems = [
  {
    id: 'group-therapy',
    href: '/news/group-therapy',
    title: 'Групповая терапия: открыт новый поток записи',
    description: 'Запись на сессии по работе с тревогой.',
    date: '7 апр.',
    delay: '0.18s',
  },
  {
    id: 'tests-update',
    href: '/news/tests-update',
    title: 'Обновлены тесты самодиагностики',
    description: 'Новые инструменты для оценки эмоционального состояния.',
    date: '2 апр.',
    delay: '0.24s',
  },
  {
    id: 'new-specialist',
    href: '/news/new-specialist',
    title: 'В команду центра пришёл новый специалист',
    description: 'Клинический психолог с опытом работы с молодёжью.',
    date: '28 мар.',
    delay: '0.30s',
  },
];

export default function NewsSection() {
  useEffect(() => {
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
  }, []);

  return (
    <div className="section-wrap alt">
      <div className="container">
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Новости и события</h2>
          <a href="/news" className={styles.sectionLink}>
            Все новости →
          </a>
        </div>

        <div className={styles.newsGrid}>
          <FeaturedNews
            news={featuredNews}
            className={styles.newsAnimate}
            style={{ animationDelay: '0s' }}
          />
          <div className={styles.newsCol}>
            {smallCards.map((card) => (
              <NewsCardSmall
                key={card.id}
                news={card}
                className={styles.newsAnimate}
                style={{ animationDelay: card.delay }}
              />
            ))}
          </div>
        </div>

        <div className={styles.newsList}>
          {listItems.map((item) => (
            <NewsListItem
              key={item.id}
              news={item}
              className={styles.newsAnimate}
              style={{ animationDelay: item.delay }}
            />
          ))}
        </div>

        <div className={styles.pagination}>
          <button className={styles.pgBtn}>← Пред</button>
          <button className={`${styles.pgNum} ${styles.active}`}>1</button>
          <button className={styles.pgNum}>2</button>
          <button className={styles.pgNum}>3</button>
          <span className={styles.pgDots}>…</span>
          <button className={styles.pgNum}>10</button>
          <button className={styles.pgNum}>11</button>
          <button className={styles.pgNum}>12</button>
          <button className={styles.pgBtn}>След →</button>
        </div>
      </div>
    </div>
  );
}
