import FeaturedNews from '../../../features/news/components/FeaturedNews';
import NewsListItem from '../../../features/news/components/NewsListItem';
import styles from './NewsPage.module.css';

export default function NewsGrid({ items }) {
  if (!items.length) {
    return <p className={styles.empty}>Новостей пока нет.</p>;
  }

  const [featured, ...rest] = items;

  return (
    <div className={styles.grid}>
      <FeaturedNews news={featured} className="" />
      {rest.length > 0 && (
        <ul className={styles.list}>
          {rest.map((item) => (
            <li key={item.id}>
              <NewsListItem news={item} className="" />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
