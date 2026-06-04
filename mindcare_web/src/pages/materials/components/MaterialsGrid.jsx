import MaterialCard from './MaterialCard';
import styles from './MaterialsGrid.module.css';

// Заглушка-скелетон пока данные грузятся
function SkeletonCard() {
  return <div className={styles.skeleton} aria-hidden="true" />;
}

export default function MaterialsGrid({ items, loading }) {
  if (loading && !items.length) {
    return (
      <div className={styles.grid}>
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  if (!items.length) {
    return (
      <p className={styles.empty}>
        Ничего не найдено. Попробуйте изменить параметры поиска.
      </p>
    );
  }

  return (
    <div className={styles.grid}>
      {items.map(item => (
        <MaterialCard key={item.id} item={item} />
      ))}
    </div>
  );
}
