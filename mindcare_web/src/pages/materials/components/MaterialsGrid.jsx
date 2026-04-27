import MaterialCard from './MaterialCard';
import styles from './MaterialsGrid.module.css';

export default function MaterialsGrid({ items }) {
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
