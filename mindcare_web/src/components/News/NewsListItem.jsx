import { Link } from 'react-router-dom';
import styles from './NewsSection.module.css';
import { ArrowRightIcon } from '../icons';

const ThumbIcon = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
    <path
      d="M2 9h14M9 2l7 7-7 7"
      stroke="#8B6F47"
      strokeWidth="1.3"
      strokeLinecap="round"
    />
  </svg>
);

export default function NewsListItem({ news, className, style }) {
  return (
    <Link
      to={`/news/${news.id}`}
      className={`${styles.newsListItem} ${className}`}
      style={style}
    >
      <div className={styles.newsListThumb}>
        <ThumbIcon />
      </div>
      <div className={styles.newsListContent}>
        <div className={styles.newsListH}>{news.title}</div>
        <div className={styles.newsListDesc}>{news.description}</div>
      </div>
      <div className={styles.newsListDate}>{news.date}</div>
      <div className={styles.newsListArrow} aria-hidden="true">
        <ArrowRightIcon width={15} height={15} />
      </div>
    </Link>
  );
}
