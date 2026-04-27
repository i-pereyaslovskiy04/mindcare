import styles from './MaterialsToolbar.module.css';
import { CATEGORIES } from './mockMaterials';
import FilterDropdown from './FilterDropdown';

const SearchIcon = () => (
  <svg
    className={styles.searchIcon}
    width="16" height="16" viewBox="0 0 16 16"
    fill="none" aria-hidden="true"
  >
    <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.4" />
    <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

const CATEGORY_ITEMS = [
  { value: '', label: 'Категория' },
  ...CATEGORIES.map(c => ({ value: c, label: c })),
];

const SORT_ITEMS = [
  { value: 'newest', label: 'Сначала новые' },
  { value: 'oldest', label: 'Сначала старые' },
];

export default function MaterialsToolbar({ search, category, sort, onSearch, onCategory, onSort }) {
  return (
    <div className={styles.toolbar} role="search">
      <div className={styles.searchWrap}>
        <SearchIcon />
        <input
          className={styles.searchInput}
          type="search"
          placeholder="Поиск по материалам…"
          value={search}
          onChange={e => onSearch(e.target.value)}
          aria-label="Поиск по материалам"
        />
      </div>

      <span className={styles.sep} aria-hidden="true" />

      <FilterDropdown
        items={CATEGORY_ITEMS}
        value={category}
        onChange={onCategory}
        placeholder="Категория"
        className={styles.filterWrap}
      />

      <span className={styles.sep} aria-hidden="true" />

      <FilterDropdown
        items={SORT_ITEMS}
        value={sort}
        onChange={onSort}
        placeholder="Сортировка"
        align="right"
        className={`${styles.filterWrap} ${styles.filterWrapLast}`}
      />
    </div>
  );
}
