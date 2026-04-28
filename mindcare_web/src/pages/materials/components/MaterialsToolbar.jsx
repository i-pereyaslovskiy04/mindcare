import styles from './MaterialsToolbar.module.css';
import { CATEGORIES } from './mockMaterials';
import MultiSelect from '../../../components/UI/MultiSelect/MultiSelect';

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

const CATEGORY_OPTIONS = CATEGORIES.map(c => ({ value: c, label: c }));

const SORT_OPTIONS = [
  { value: 'newest', label: 'Сначала новые' },
  { value: 'oldest', label: 'Сначала старые' },
];

export default function MaterialsToolbar({ search, category, sort, onSearch, onCategory, onSort }) {
  return (
    <div className={styles.filterBar} role="search">

      {/* ── Search ── */}
      <div className={styles.searchSegment}>
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

      {/* hidden on mobile (search gets border-bottom instead) */}
      <span className={`${styles.sep} ${styles.sepAfterSearch}`} aria-hidden="true" />

      {/* ── Categories ── */}
      <MultiSelect
        options={CATEGORY_OPTIONS}
        value={category}
        onChange={onCategory}
        placeholder="Категория"
        flat
        className={styles.catSegment}
      />

      <span className={styles.sep} aria-hidden="true" />

      {/* ── Sort ── */}
      <MultiSelect
        options={SORT_OPTIONS}
        value={sort}
        onChange={onSort}
        placeholder="Сортировка"
        single
        flat
        className={styles.sortSegment}
      />

    </div>
  );
}
