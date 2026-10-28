import FilterChip from '../../../components/UI/FilterChip/FilterChip';
import styles from './FiltersDropdown.module.css';

const XIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
    <path d="M2 2l9 9M11 2L2 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const CheckIcon = () => (
  <svg width="9" height="8" viewBox="0 0 9 8" fill="none" aria-hidden="true">
    <path d="M1 4l2.5 2.5L8 1" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export default function FiltersDropdown({
  onClose,
  category,
  onCategoryChange,
  categoryOptions,
  onClear,
}) {
  // Один выбор: API статей принимает ровно один category_id.
  const toggleCategory = (value) =>
    onCategoryChange(category === value ? null : value);

  const hasActiveFilters = category != null;

  return (
    <div className={styles.panel}>

      <div className={styles.header}>
        <span className={styles.headerTitle}>Фильтры</span>
        <button type="button" className={styles.closeBtn} onClick={onClose} aria-label="Закрыть фильтры">
          <XIcon />
        </button>
      </div>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Тип материала</h3>
        <div className={styles.tagGrid}>
          {categoryOptions.map((opt) => {
            const active = category === opt.value;
            return (
              <FilterChip
                key={opt.value}
                active={active}
                onClick={() => toggleCategory(opt.value)}
                icon={active ? <CheckIcon /> : null}
              >
                {opt.label}
              </FilterChip>
            );
          })}
        </div>
      </section>

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
