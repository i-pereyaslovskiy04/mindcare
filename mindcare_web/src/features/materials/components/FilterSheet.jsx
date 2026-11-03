import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import FilterSections from './FilterSections';
import styles from './FilterSheet.module.css';

const XIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
    <path d="M2 2l9 9M11 2L2 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
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
  onClear,
  ...filters
}) {
  const hasActiveFilters = filters.category != null || filters.tag != null;

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

        <FilterSections {...filters} size="md" classes={styles} />

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
