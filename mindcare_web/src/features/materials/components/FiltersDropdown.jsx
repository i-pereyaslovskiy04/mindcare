import FilterSections from './FilterSections';
import styles from './FiltersDropdown.module.css';

const XIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
    <path d="M2 2l9 9M11 2L2 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

export default function FiltersDropdown({
  onClose,
  onClear,
  ...filters
}) {
  const hasActiveFilters = filters.category != null || filters.tag != null;

  return (
    <div className={styles.panel}>

      <div className={styles.header}>
        <span className={styles.headerTitle}>Фильтры</span>
        <button type="button" className={styles.closeBtn} onClick={onClose} aria-label="Закрыть фильтры">
          <XIcon />
        </button>
      </div>

      <FilterSections {...filters} classes={styles} />

      {hasActiveFilters && (
        <div className={styles.clearSection}>
          <button type="button" className={styles.clearBtn} onClick={onClear}>
            Очистить фильтры
          </button>
        </div>
      )}

    </div>
  );
}
