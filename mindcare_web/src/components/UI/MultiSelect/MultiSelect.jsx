import { useState, useRef, useEffect } from 'react';
import styles from './multiSelect.module.css';

const XIcon = () => (
  <svg width="8" height="8" viewBox="0 0 8 8" fill="none" aria-hidden="true">
    <path d="M1 1l6 6M7 1L1 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
);

const ChevronIcon = () => (
  <svg width="10" height="6" viewBox="0 0 10 6" fill="none" aria-hidden="true">
    <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const CheckIcon = () => (
  <svg width="9" height="7" viewBox="0 0 9 7" fill="none" aria-hidden="true">
    <path d="M1 3.5l2.5 2.5L8 1" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const SearchIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
    <circle cx="5.5" cy="5.5" r="4" stroke="currentColor" strokeWidth="1.3" />
    <path d="M8.5 8.5L11.5 11.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
  </svg>
);

export default function MultiSelect({
  options,
  value,
  onChange,
  placeholder,
  single = false,
  flat = false,
  className = '',
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const wrapRef = useRef(null);
  const searchRef = useRef(null);

  const selected = single
    ? (value ? [value] : [])
    : (Array.isArray(value) ? value : []);

  useEffect(() => {
    if (!isOpen) return;
    const handler = e => {
      if (!wrapRef.current?.contains(e.target)) close();
    };
    document.addEventListener('mousedown', handler, true);
    return () => document.removeEventListener('mousedown', handler, true);
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && searchRef.current) {
      searchRef.current.focus();
    }
  }, [isOpen]);

  const close = () => { setIsOpen(false); setSearch(''); };
  const toggle = () => setIsOpen(v => !v);

  const handleSelect = optValue => {
    if (single) {
      onChange(optValue);
      close();
    } else {
      const next = selected.includes(optValue)
        ? selected.filter(v => v !== optValue)
        : [...selected, optValue];
      onChange(next);
    }
  };

  const removeTag = (optValue, e) => {
    e.stopPropagation();
    onChange(selected.filter(v => v !== optValue));
  };

  const filteredOptions = options.filter(o =>
    o.label.toLowerCase().includes(search.toLowerCase())
  );

  const selectedOptions = selected
    .map(v => options.find(o => o.value === v))
    .filter(Boolean);

  const wrapClass = [
    styles.wrap,
    isOpen ? styles.wrapOpen : '',
    flat ? styles.wrapFlat : '',
    className,
  ].filter(Boolean).join(' ');

  return (
    <div className={wrapClass} ref={wrapRef}>
      <div
        className={styles.trigger}
        onClick={toggle}
        role="combobox"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
      >
        <div className={styles.valueArea}>
          {selectedOptions.length > 0 ? (
            single ? (
              <span className={styles.singleValue}>{selectedOptions[0].label}</span>
            ) : (
              selectedOptions.map(opt => (
                <span key={opt.value} className={styles.tag}>
                  <span className={styles.tagLabel}>{opt.label}</span>
                  <button
                    type="button"
                    className={styles.tagRemove}
                    onClick={e => removeTag(opt.value, e)}
                    aria-label={`Убрать ${opt.label}`}
                  >
                    <XIcon />
                  </button>
                </span>
              ))
            )
          ) : (
            <span className={styles.placeholder}>{placeholder}</span>
          )}
        </div>

        <span className={`${styles.chevron} ${isOpen ? styles.chevronUp : ''}`} aria-hidden="true">
          <ChevronIcon />
        </span>
      </div>

      <div
        className={`${styles.panel} ${isOpen ? styles.panelOpen : ''}`}
        aria-hidden={!isOpen}
      >
        <div className={styles.panelSearch}>
          <span className={styles.panelSearchIcon}><SearchIcon /></span>
          <input
            ref={searchRef}
            type="text"
            className={styles.panelSearchInput}
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Поиск…"
            tabIndex={isOpen ? 0 : -1}
            aria-label="Поиск в списке"
          />
        </div>

        <ul className={styles.list} role="listbox" aria-multiselectable={!single}>
          {filteredOptions.length > 0 ? (
            filteredOptions.map(opt => (
              <li key={opt.value} role="none">
                <button
                  type="button"
                  role="option"
                  aria-selected={selected.includes(opt.value)}
                  className={`${styles.item} ${selected.includes(opt.value) ? styles.itemActive : ''}`}
                  onClick={() => handleSelect(opt.value)}
                  tabIndex={isOpen ? 0 : -1}
                >
                  {!single && (
                    <span
                      className={`${styles.checkbox} ${selected.includes(opt.value) ? styles.checkboxChecked : ''}`}
                      aria-hidden="true"
                    >
                      {selected.includes(opt.value) && <CheckIcon />}
                    </span>
                  )}
                  <span>{opt.label}</span>
                </button>
              </li>
            ))
          ) : (
            <li className={styles.empty}>Ничего не найдено</li>
          )}
        </ul>
      </div>
    </div>
  );
}
