import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import FilterChip from '../../../components/UI/FilterChip/FilterChip';
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

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(root) {
  return Array.from(root?.querySelectorAll(FOCUSABLE) ?? []);
}

/**
 * Мобильная панель фильтров — модальный диалог: при открытии фокус уходит на
 * первый контрол панели, Tab / Shift+Tab циклически остаются внутри, Escape
 * закрывает (обработчик в SearchBar), фокус после закрытия возвращает
 * SearchBar на кнопку «Фильтры».
 */
export default function FilterSheet({
  sheetRef,
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

  useEffect(() => {
    focusables(sheetRef.current)[0]?.focus();
  }, [sheetRef]);

  const trapTab = (e) => {
    if (e.key !== 'Tab') return;
    const items = focusables(sheetRef.current);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    const inside = sheetRef.current?.contains(active);
    if (e.shiftKey && (active === first || !inside)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (active === last || !inside)) {
      e.preventDefault();
      first.focus();
    }
  };

  return createPortal(
    <>
      <div className={styles.overlay} onClick={onClose} aria-hidden="true" />

      <div
        ref={sheetRef}
        className={styles.sheet}
        role="dialog"
        aria-modal="true"
        aria-label="Фильтры"
        onKeyDown={trapTab}
      >

        <div className={styles.header}>
          <span className={styles.headerTitle}>Фильтры</span>
          <button type="button" className={styles.closeBtn} onClick={onClose} aria-label="Закрыть панель фильтров">
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
                  size="md"
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
    </>,
    document.body,
  );
}
