import CompactMaterialCard from './CompactMaterialCard';
import MaterialCard from './MaterialCard';
import styles from './MaterialsGrid.module.css';

// Заглушка-скелетон пока данные грузятся
function SkeletonCard({ compact }) {
  return (
    <div
      className={compact ? `${styles.skeleton} ${styles.skeletonCompact}` : styles.skeleton}
      aria-hidden="true"
    />
  );
}

// getItemPath(id) — адрес чтения материала (см. MaterialCard.to).
// emptyText — текст пустой выдачи (зависит от того, применены ли фильтры).
// variant: 'card' — публичные карточки; 'compact' — компактные карточки кабинетов.
// favorites (только compact): { isFavorite(id), toggle(item), pendingId } или null.
export default function MaterialsGrid({
  items,
  loading,
  getItemPath,
  emptyText = 'Ничего не найдено. Попробуйте изменить параметры поиска.',
  variant = 'card',
  favorites = null,
}) {
  const compact = variant === 'compact';
  const gridClass = compact ? `${styles.grid} ${styles.compact}` : styles.grid;

  if (loading && !items.length) {
    return (
      <div className={gridClass}>
        {Array.from({ length: compact ? 8 : 6 }).map((_, i) => (
          <SkeletonCard key={i} compact={compact} />
        ))}
      </div>
    );
  }

  if (!items.length) {
    return (
      <p className={styles.empty}>{emptyText}</p>
    );
  }

  return (
    <div className={gridClass}>
      {items.map(item => (compact ? (
        <CompactMaterialCard
          key={item.id}
          item={item}
          to={getItemPath?.(item.id)}
          favorite={favorites ? favorites.isFavorite(item.id) : undefined}
          onToggleFavorite={favorites?.toggle}
          favoritePending={favorites?.pendingId === item.id}
        />
      ) : (
        <MaterialCard key={item.id} item={item} to={getItemPath?.(item.id)} />
      )))}
    </div>
  );
}
