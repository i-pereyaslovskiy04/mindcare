import { useState, useRef, useEffect, useLayoutEffect, useCallback, useId } from 'react';
import { createPortal } from 'react-dom';
import styles from './Select.module.css';

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

/**
 * Custom single-select dropdown.
 * Renders the panel via portal (position:fixed) to escape modal overflow:hidden.
 *
 * Props:
 *   label       — field label text
 *   placeholder — shown when nothing selected
 *   value       — currently selected option value (string or number)
 *   options     — [{ value, label }]
 *   onChange    — (value) => void
 *   disabled    — boolean
 *   error       — error message string
 *   displayLabel — optional label to show when `value` has no matching option
 *                  (e.g. a current value intentionally excluded from selectable
 *                  options). Display only — it never appears in the dropdown.
 */
export default function Select({
  label,
  placeholder = 'Выберите…',
  value,
  options = [],
  onChange,
  disabled = false,
  error,
  className,
  style,
  panelZIndex = 2100,
  displayLabel,
}) {
  const [isOpen, setIsOpen]       = useState(false);
  const [activeIndex, setActive]  = useState(-1);
  const [panelPos, setPanelPos]   = useState({ top: 0, left: 0, minWidth: 0 });

  const controlRef = useRef(null);
  const wrapRef    = useRef(null);
  const panelRef   = useRef(null);
  const listboxId  = useId();
  const labelId    = useId();

  const selectedOption = options.find(o => String(o.value) === String(value)) ?? null;

  const calcPos = useCallback(() => {
    if (!controlRef.current) return;
    const r = controlRef.current.getBoundingClientRect();
    const triggerW = r.width;
    // Use actual rendered panel width when available; fall back to trigger width
    const panelW = panelRef.current ? panelRef.current.offsetWidth : triggerW;
    // Center panel relative to trigger, then clamp to viewport
    const centeredLeft = r.left + triggerW / 2 - panelW / 2;
    const left = Math.max(12, Math.min(centeredLeft, window.innerWidth - panelW - 12));
    setPanelPos({ top: r.bottom + 4, left, minWidth: triggerW });
  }, []);

  const openDropdown = useCallback(() => {
    calcPos();
    const idx = options.findIndex(o => String(o.value) === String(value));
    setActive(idx >= 0 ? idx : -1);
    setIsOpen(true);
  }, [calcPos, options, value]);

  const closeDropdown = useCallback(() => {
    setIsOpen(false);
    setActive(-1);
  }, []);

  const handleSelect = useCallback((optValue) => {
    onChange(optValue);
    closeDropdown();
    controlRef.current?.focus();
  }, [onChange, closeDropdown]);

  // Close on outside click (capture phase catches clicks on portal panel too)
  useEffect(() => {
    if (!isOpen) return;
    const onOutside = (e) => {
      const panel = document.getElementById(listboxId);
      if (!wrapRef.current?.contains(e.target) && !panel?.contains(e.target)) {
        closeDropdown();
      }
    };
    document.addEventListener('mousedown', onOutside, true);
    return () => document.removeEventListener('mousedown', onOutside, true);
  }, [isOpen, listboxId, closeDropdown]);

  // Reposition panel on scroll or resize
  useEffect(() => {
    if (!isOpen) return;
    const reposition = () => calcPos();
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
    return () => {
      window.removeEventListener('scroll', reposition, true);
      window.removeEventListener('resize', reposition);
    };
  }, [isOpen, calcPos]);

  // After panel mounts we know its actual offsetWidth — recenter without flicker
  useLayoutEffect(() => {
    if (!isOpen) return;
    calcPos();
  }, [isOpen, calcPos]);

  const handleKeyDown = (e) => {
    if (disabled) return;
    switch (e.key) {
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (!isOpen) openDropdown();
        else if (activeIndex >= 0 && activeIndex < options.length) {
          handleSelect(options[activeIndex].value);
        }
        break;
      case 'Escape':
        if (isOpen) {
          e.preventDefault();
          e.stopPropagation(); // keep modal open; only close the dropdown
          closeDropdown();
        }
        break;
      case 'ArrowDown':
        e.preventDefault();
        if (!isOpen) openDropdown();
        else setActive(i => Math.min(i + 1, options.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        if (!isOpen) openDropdown();
        else setActive(i => Math.max(i - 1, 0));
        break;
      case 'Tab':
        if (isOpen) closeDropdown();
        break;
      default:
        break;
    }
  };

  return (
    <div className={[styles.wrap, className].filter(Boolean).join(' ')} ref={wrapRef} style={style}>
      {label && <span id={labelId} className={styles.label}>{label}</span>}

      <button
        ref={controlRef}
        type="button"
        className={[
          styles.control,
          isOpen  && styles.controlOpen,
          error   && styles.controlError,
        ].filter(Boolean).join(' ')}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={isOpen ? listboxId : undefined}
        aria-labelledby={label ? labelId : undefined}
        disabled={disabled}
        onClick={() => (isOpen ? closeDropdown() : openDropdown())}
        onKeyDown={handleKeyDown}
      >
        <span className={selectedOption || displayLabel ? styles.value : styles.placeholder}>
          {selectedOption ? selectedOption.label : (displayLabel ?? placeholder)}
        </span>
        <span className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`} aria-hidden="true">
          <ChevronIcon />
        </span>
      </button>

      {isOpen && createPortal(
        <ul
          ref={panelRef}
          id={listboxId}
          role="listbox"
          className={styles.panel}
          style={{
            top: panelPos.top,
            left: panelPos.left,
            minWidth: panelPos.minWidth,
            maxWidth: Math.min(360, window.innerWidth - 24),
            zIndex: panelZIndex,
          }}
          aria-label={label}
        >
          {options.length === 0 ? (
            <li className={styles.empty} role="presentation">
              Нет доступных вариантов
            </li>
          ) : (
            options.map((opt, idx) => {
              const isSelected = String(opt.value) === String(value);
              const isActive   = idx === activeIndex;
              return (
                <li
                  key={opt.value}
                  role="option"
                  aria-selected={isSelected}
                  className={[
                    styles.option,
                    isSelected && styles.optionSelected,
                    isActive   && styles.optionActive,
                  ].filter(Boolean).join(' ')}
                  onMouseDown={(e) => { e.preventDefault(); handleSelect(opt.value); }}
                  onMouseEnter={() => setActive(idx)}
                >
                  <span className={styles.optionCheck} aria-hidden="true">
                    {isSelected && <CheckIcon />}
                  </span>
                  <span className={styles.optionLabel} title={opt.label}>{opt.label}</span>
                </li>
              );
            })
          )}
        </ul>,
        document.body
      )}

      {error && <span className={styles.error} role="alert">{error}</span>}
    </div>
  );
}
