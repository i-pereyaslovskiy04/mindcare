import { useState, useRef, useEffect } from 'react';
import styles from './SearchBar.module.css';
import FiltersDropdown from './FiltersDropdown';
import FilterSheet from './FilterSheet';

const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.4" />
    <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

const FilterIcon = () => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
    <path d="M1.5 3.5h12M4 7.5h7M6.5 11.5h2"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const XTinyIcon = () => (
  <svg width="8" height="8" viewBox="0 0 8 8" fill="none" aria-hidden="true">
    <path d="M1 1l6 6M7 1L1 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
);

export default function SearchBar({
  onQueryChange,
  selectedTags,
  onTagsChange,
  sort,
  onSortChange,
  tagOptions,
}) {
  const [inputValue, setInputValue] = useState('');
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia('(max-width: 768px)').matches
  );

  const debounceRef = useRef(null);
  // Wraps the filter button + desktop dropdown; position:relative anchors the dropdown
  const filterWrapRef = useRef(null);
  // Used only for mobile sheet click-outside (panel is in a portal, outside filterWrapRef)
  const sheetRef = useRef(null);

  // Track breakpoint changes
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    const handler = e => setIsMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // Close on outside click.
  // Desktop: filterWrapRef covers button + dropdown → single check.
  // Mobile:  filterWrapRef covers button, sheetRef covers portaled sheet.
  useEffect(() => {
    if (!isFilterOpen) return;
    const handler = e => {
      const inWrap = filterWrapRef.current?.contains(e.target);
      const inSheet = sheetRef.current?.contains(e.target);
      if (!inWrap && !inSheet) setIsFilterOpen(false);
    };
    document.addEventListener('mousedown', handler, true);
    return () => document.removeEventListener('mousedown', handler, true);
  }, [isFilterOpen]);

  // Close on Escape
  useEffect(() => {
    if (!isFilterOpen) return;
    const handler = e => { if (e.key === 'Escape') setIsFilterOpen(false); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isFilterOpen]);

  const handleInputChange = e => {
    const val = e.target.value;
    setInputValue(val);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => onQueryChange(val), 300);
  };

  const clearInput = () => {
    setInputValue('');
    clearTimeout(debounceRef.current);
    onQueryChange('');
  };

  const removeTag = tag => onTagsChange(selectedTags.filter(t => t !== tag));

  const handleClearAll = () => {
    onTagsChange([]);
    onSortChange('newest');
  };

  const activeFilterCount = selectedTags.length + (sort !== 'newest' ? 1 : 0);

  const sharedProps = {
    onClose: () => setIsFilterOpen(false),
    selectedTags,
    onTagsChange,
    sort,
    onSortChange,
    tagOptions,
    onClear: handleClearAll,
  };

  return (
    <div className={styles.searchBar}>

      {/* ── Row: input + filter button ── */}
      <div className={styles.inputRow}>

        <div className={styles.inputWrap}>
          <span className={styles.searchIcon}><SearchIcon /></span>
          <input
            className={styles.input}
            type="text"
            placeholder="Поиск по материалам…"
            value={inputValue}
            onChange={handleInputChange}
            aria-label="Поиск по материалам"
          />
          {inputValue && (
            <button
              className={styles.clearInputBtn}
              onClick={clearInput}
              aria-label="Очистить поиск"
            >
              <XTinyIcon />
            </button>
          )}
        </div>

        {/* position:relative here — FiltersDropdown (absolute) anchors to this div */}
        <div className={styles.filterBtnWrap} ref={filterWrapRef}>
          <button
            className={[
              styles.filterBtn,
              activeFilterCount > 0 ? styles.filterBtnActive : '',
              isFilterOpen ? styles.filterBtnOpen : '',
            ].filter(Boolean).join(' ')}
            onClick={() => setIsFilterOpen(v => !v)}
            aria-label={`Фильтры${activeFilterCount > 0 ? `, выбрано: ${activeFilterCount}` : ''}`}
            aria-expanded={isFilterOpen}
            aria-haspopup="menu"
          >
            <FilterIcon />
            {activeFilterCount > 0 && (
              <span className={styles.badge} aria-hidden="true">{activeFilterCount}</span>
            )}
          </button>

          {/* Desktop: true dropdown, lives inside the relative wrapper */}
          {isFilterOpen && !isMobile && (
            <FiltersDropdown {...sharedProps} />
          )}
        </div>

      </div>

      {/* ── Selected tag chips ── */}
      {selectedTags.length > 0 && (
        <div className={styles.chipsRow} aria-label="Активные фильтры">
          {selectedTags.map(tag => (
            <span key={tag} className={styles.chip}>
              {tag}
              <button
                className={styles.chipRemove}
                onClick={() => removeTag(tag)}
                aria-label={`Убрать фильтр «${tag}»`}
              >
                <XTinyIcon />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Mobile: portal bottom sheet, completely outside the layout tree */}
      {isFilterOpen && isMobile && (
        <FilterSheet sheetRef={sheetRef} {...sharedProps} />
      )}

    </div>
  );
}
