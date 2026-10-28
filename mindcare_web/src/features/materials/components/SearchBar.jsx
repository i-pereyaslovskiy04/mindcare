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

/**
 * Поиск и фильтр библиотеки материалов. Только то, что принимает API статей:
 * текст поиска (debounce 300 мс), одна категория («Тип материала») и одна тема
 * («Тема»; варианты — темы опубликованных статей). Без вариантов обоих
 * фильтров кнопка фильтров не показывается.
 */
export default function SearchBar({
  onQueryChange,
  category,
  onCategoryChange,
  categoryOptions = [],
  tag = null,
  onTagChange = () => {},
  tagOptions = [],
}) {
  const [inputValue,    setInputValue]    = useState('');
  const [isFilterOpen,  setIsFilterOpen]  = useState(false);
  const [isMobile,      setIsMobile]      = useState(
    () => window.matchMedia('(max-width: 768px)').matches,
  );

  const debounceRef   = useRef(null);
  const filterWrapRef = useRef(null);
  const sheetRef      = useRef(null);
  const filterBtnRef  = useRef(null);
  const wasOpenRef    = useRef(false);

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    const handler = (e) => setIsMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  useEffect(() => () => clearTimeout(debounceRef.current), []);

  // Возврат фокуса на кнопку «Фильтры» после закрытия панели (Escape,
  // «Закрыть», подложка, выбор). Если пользователь сам перевёл фокус на другой
  // элемент (клик вне панели), фокус не перехватывается.
  useEffect(() => {
    if (wasOpenRef.current && !isFilterOpen) {
      const active = document.activeElement;
      if (!active || active === document.body) filterBtnRef.current?.focus();
    }
    wasOpenRef.current = isFilterOpen;
  }, [isFilterOpen]);

  useEffect(() => {
    if (!isFilterOpen) return;
    const handler = (e) => {
      const inWrap  = filterWrapRef.current?.contains(e.target);
      const inSheet = sheetRef.current?.contains(e.target);
      if (!inWrap && !inSheet) setIsFilterOpen(false);
    };
    document.addEventListener('mousedown', handler, true);
    return () => document.removeEventListener('mousedown', handler, true);
  }, [isFilterOpen]);

  useEffect(() => {
    if (!isFilterOpen) return;
    const handler = (e) => { if (e.key === 'Escape') setIsFilterOpen(false); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isFilterOpen]);

  const handleInputChange = (e) => {
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

  const selectedCategory = categoryOptions.find((o) => o.value === category) || null;
  const selectedTag = tagOptions.find((o) => o.value === tag) || null;
  const activeChips = [
    selectedCategory && { key: 'category', label: selectedCategory.label, remove: () => onCategoryChange(null) },
    selectedTag && { key: 'tag', label: selectedTag.label, remove: () => onTagChange(null) },
  ].filter(Boolean);
  const activeFilterCount = activeChips.length;
  const hasFilters = categoryOptions.length > 0 || tagOptions.length > 0;

  const sharedProps = {
    onClose: () => setIsFilterOpen(false),
    category,
    onCategoryChange,
    categoryOptions,
    tag,
    onTagChange,
    tagOptions,
    onClear: () => { onCategoryChange(null); onTagChange(null); },
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
              type="button"
              className={styles.clearInputBtn}
              onClick={clearInput}
              aria-label="Очистить поиск"
            >
              <XTinyIcon />
            </button>
          )}
        </div>

        {/* position:relative — FiltersDropdown (absolute) anchors to this div */}
        {hasFilters && (
        <div className={styles.filterBtnWrap} ref={filterWrapRef}>
          <button
            ref={filterBtnRef}
            type="button"
            className={[
              styles.filterBtn,
              activeFilterCount > 0 ? styles.filterBtnActive : '',
              isFilterOpen ? styles.filterBtnOpen : '',
            ].filter(Boolean).join(' ')}
            onClick={() => setIsFilterOpen((v) => !v)}
            aria-label={`Фильтры${activeFilterCount > 0 ? `, выбрано: ${activeFilterCount}` : ''}`}
            aria-expanded={isFilterOpen}
            aria-haspopup="true"
          >
            <FilterIcon />
            {activeFilterCount > 0 && (
              <span className={styles.badge} aria-hidden="true">{activeFilterCount}</span>
            )}
          </button>

          {isFilterOpen && !isMobile && (
            <FiltersDropdown {...sharedProps} />
          )}
        </div>
        )}

      </div>

      {/* ── Selected filter chips ── */}
      {activeChips.length > 0 && (
        <div className={styles.chipsRow} aria-label="Активные фильтры">
          {activeChips.map((chip) => (
            <span key={chip.key} className={styles.chip}>
              {chip.label}
              <button
                type="button"
                className={styles.chipRemove}
                onClick={chip.remove}
                aria-label={`Убрать фильтр «${chip.label}»`}
              >
                <XTinyIcon />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Mobile: portal bottom sheet */}
      {hasFilters && isFilterOpen && isMobile && (
        <FilterSheet sheetRef={sheetRef} {...sharedProps} />
      )}

    </div>
  );
}
