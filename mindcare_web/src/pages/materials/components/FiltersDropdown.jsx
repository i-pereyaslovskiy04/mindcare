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

const SORT_OPTIONS = [
  { value: 'newest', label: 'Сначала новые' },
  { value: 'oldest', label: 'Сначала старые' },
];

export default function FiltersDropdown({
  onClose,
  selectedTags,
  onTagsChange,
  selectedTopics,
  onTopicsChange,
  sort,
  onSortChange,
  tagOptions,
  topicOptions,
  onClear,
}) {
  const toggleTag = (tag) =>
    onTagsChange(
      selectedTags.includes(tag)
        ? selectedTags.filter((t) => t !== tag)
        : [...selectedTags, tag],
    );

  const toggleTopic = (topic) =>
    onTopicsChange(
      selectedTopics.includes(topic)
        ? selectedTopics.filter((t) => t !== topic)
        : [...selectedTopics, topic],
    );

  const hasActiveFilters = selectedTags.length > 0 || selectedTopics.length > 0 || sort !== 'newest';

  return (
    <div className={styles.panel}>

      <div className={styles.header}>
        <span className={styles.headerTitle}>Фильтры</span>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Закрыть фильтры">
          <XIcon />
        </button>
      </div>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Тип</h3>
        <div className={styles.tagGrid}>
          {tagOptions.map((opt) => {
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
        <h3 className={styles.sectionTitle}>Тема</h3>
        <div className={styles.tagGrid}>
          {topicOptions.map((opt) => {
            const active = selectedTopics.includes(opt.value);
            return (
              <button
                key={opt.value}
                className={`${styles.tagBtn} ${active ? styles.tagBtnActive : ''}`}
                onClick={() => toggleTopic(opt.value)}
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
          {SORT_OPTIONS.map((opt) => (
            <label key={opt.value} className={styles.radioLabel}>
              <input
                type="radio"
                name="filtersSortDesktop"
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
  );
}
