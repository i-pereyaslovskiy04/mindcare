import { createPortal } from 'react-dom';
import styles from './FilterSheet.module.css';

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

const SORT_OPTIONS = [
  { value: 'newest', label: 'Сначала новые' },
  { value: 'oldest', label: 'Сначала старые' },
];

export default function FilterSheet({
  sheetRef,
  onClose,
  selectedTags,
  onTagsChange,
  sort,
  onSortChange,
  tagOptions,
  onClear,
}) {
  const toggleTag = tag =>
    onTagsChange(
      selectedTags.includes(tag)
        ? selectedTags.filter(t => t !== tag)
        : [...selectedTags, tag]
    );

  const hasActiveFilters = selectedTags.length > 0 || sort !== 'newest';

  return createPortal(
    <>
      <div className={styles.overlay} onClick={onClose} aria-hidden="true" />

      <div
        ref={sheetRef}
        className={styles.sheet}
        role="dialog"
        aria-modal="true"
        aria-label="Фильтры"
      >

        <div className={styles.header}>
          <span className={styles.headerTitle}>Фильтры</span>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Закрыть панель фильтров">
            <XIcon />
          </button>
        </div>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>Категория</h3>
          <div className={styles.tagGrid}>
            {tagOptions.map(opt => {
              const active = selectedTags.includes(opt.value);
              return (
                <button
                  key={opt.value}
                  className={`${styles.tagBtn} ${active ? styles.tagBtnActive : ''}`}
                  onClick={() => toggleTag(opt.value)}
                  aria-pressed={active}
                >
                  {active && <CheckIcon />}
                  {opt.label}
                </button>
              );
            })}
          </div>
        </section>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>Сортировка</h3>
          <div className={styles.sortList}>
            {SORT_OPTIONS.map(opt => (
              <label key={opt.value} className={styles.radioLabel}>
                <input
                  type="radio"
                  name="filtersSortMobile"
                  value={opt.value}
                  checked={sort === opt.value}
                  onChange={() => onSortChange(opt.value)}
                  className={styles.radioInput}
                />
                <span className={styles.radioCustom} aria-hidden="true" />
                <span>{opt.label}</span>
              </label>
            ))}
          </div>
        </section>

        {hasActiveFilters && (
          <div className={styles.clearSection}>
            <button className={styles.clearBtn} onClick={onClear}>
              Очистить фильтры
            </button>
          </div>
        )}

      </div>
    </>,
    document.body
  );
}
