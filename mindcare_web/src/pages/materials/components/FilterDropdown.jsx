import { useState, useRef, useEffect } from 'react';
import styles from './FilterDropdown.module.css';

const Chevron = () => (
  <svg width="10" height="6" viewBox="0 0 10 6" fill="none" aria-hidden="true">
    <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export default function FilterDropdown({ items, value, onChange, placeholder, align = 'left', className = '' }) {
  const [isOpen, setIsOpen] = useState(false);
  const wrapRef = useRef(null);

  const current = items.find(i => i.value === value);
  // always show the matched label as value text (not placeholder)
  // so "Категория" and "Сначала новые" render in the same colour
  const displayValue = current?.label ?? '';

  useEffect(() => {
    if (!isOpen) return;
    // capture phase: fires before blur so item clicks register first
    const handler = e => {
      if (!wrapRef.current?.contains(e.target)) setIsOpen(false);
    };
    document.addEventListener('mousedown', handler, true);
    return () => document.removeEventListener('mousedown', handler, true);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = e => { if (e.key === 'Escape') setIsOpen(false); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen]);

  const toggle = () => setIsOpen(v => !v);

  return (
    <div className={`${styles.wrap} ${className}`} ref={wrapRef}>
      {/* readonly input — no button artifacts, no browser press styles */}
      <input
        type="text"
        className={`${styles.trigger} ${isOpen ? styles.triggerOpen : ''}`}
        readOnly
        value={displayValue}
        placeholder={placeholder}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        autoComplete="off"
        onClick={toggle}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
          if (e.key === 'Escape') setIsOpen(false);
        }}
      />

      {/* chevron overlaid on right — pointer-events:none so clicks pass to input */}
      <span className={`${styles.chevron} ${isOpen ? styles.chevronUp : ''}`} aria-hidden="true">
        <Chevron />
      </span>

      {isOpen && (
        <ul
          className={`${styles.panel} ${align === 'right' ? styles.panelRight : ''}`}
          role="listbox"
        >
          {items.map(item => (
            <li key={item.value} role="none">
              <button
                type="button"
                role="option"
                aria-selected={item.value === value}
                className={`${styles.item} ${item.value === value ? styles.itemActive : ''}`}
                onClick={() => { onChange(item.value); setIsOpen(false); }}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
