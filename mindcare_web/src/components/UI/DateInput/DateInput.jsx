import { useState, useRef, useEffect, useLayoutEffect, useCallback, useId, useMemo } from 'react';
import { createPortal } from 'react-dom';
import {
  dateOnlyToDisplay,
  dateOnlyToParts,
  partsToDateOnly,
  daysInMonth,
  firstWeekdayMonday,
  todayDateOnly,
} from './dateHelpers';
import { computePopoverPosition } from './popoverPosition';
import styles from './DateInput.module.css';

const MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

const CalendarIcon = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <rect x="2" y="3" width="12" height="11" rx="2" stroke="currentColor" strokeWidth="1.4" />
    <path d="M2 6h12M5.5 1.5v3M10.5 1.5v3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

/**
 * Стилизованное поле выбора даты (только дата, без времени и без нативного
 * datetime-local popup). Controlled: value 'YYYY-MM-DD' | '', onChange(next).
 *
 * Props: value, onChange, label?, placeholder?, disabled?, error?, id?, min?, max?
 */
export default function DateInput({
  value = '',
  onChange,
  label,
  placeholder = 'дд.мм.гггг',
  disabled = false,
  error,
  id,
  min,
  max,
  className,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [panelPos, setPanelPos] = useState({ top: 0, left: 0, direction: 'down' });

  const reactId = useId();
  const fieldId = id || `dateinput-${reactId}`;
  const dialogId = `${fieldId}-dialog`;

  const wrapRef = useRef(null);
  const controlRef = useRef(null);
  const panelRef = useRef(null);

  const selected = useMemo(() => dateOnlyToParts(value), [value]);

  // Текущий месяц в попапе: месяц выбранной даты, иначе текущий месяц.
  const initialView = useMemo(() => {
    const base = selected || dateOnlyToParts(todayDateOnly());
    return { year: base.year, month0: base.month0 };
  }, [selected]);
  const [view, setView] = useState(initialView);

  const calcPos = useCallback(() => {
    if (!controlRef.current) return;
    const r = controlRef.current.getBoundingClientRect();
    // До монтирования панели реальных размеров нет — используем дефолт,
    // useLayoutEffect пересчитает по фактическому offsetWidth/Height.
    const size = panelRef.current
      ? { width: panelRef.current.offsetWidth, height: panelRef.current.offsetHeight }
      : { width: 280, height: 320 };
    const pos = computePopoverPosition(
      r,
      size,
      { width: window.innerWidth, height: window.innerHeight },
    );
    setPanelPos(pos);
  }, []);

  const openPanel = useCallback(() => {
    if (disabled) return;
    setView(initialView);
    calcPos();
    setIsOpen(true);
  }, [disabled, initialView, calcPos]);

  const closePanel = useCallback(() => setIsOpen(false), []);

  const display = dateOnlyToDisplay(value);

  function emit(next) {
    onChange?.(next);
  }

  function selectDay(day) {
    emit(partsToDateOnly(view.year, view.month0, day));
    closePanel();
    controlRef.current?.focus();
  }

  function clear() {
    emit('');
    closePanel();
    controlRef.current?.focus();
  }

  function shiftMonth(delta) {
    setView((v) => {
      const m = v.month0 + delta;
      const year = v.year + Math.floor(m / 12);
      const month0 = ((m % 12) + 12) % 12;
      return { year, month0 };
    });
  }

  // Close on outside click (capture phase catches the portal panel too).
  useEffect(() => {
    if (!isOpen) return undefined;
    const onOutside = (e) => {
      if (!wrapRef.current?.contains(e.target) && !panelRef.current?.contains(e.target)) {
        closePanel();
      }
    };
    document.addEventListener('mousedown', onOutside, true);
    return () => document.removeEventListener('mousedown', onOutside, true);
  }, [isOpen, closePanel]);

  // Reposition on scroll/resize.
  useEffect(() => {
    if (!isOpen) return undefined;
    const reposition = () => calcPos();
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
    return () => {
      window.removeEventListener('scroll', reposition, true);
      window.removeEventListener('resize', reposition);
    };
  }, [isOpen, calcPos]);

  useLayoutEffect(() => {
    if (isOpen) calcPos();
  }, [isOpen, calcPos]);

  function handleKeyDown(e) {
    if (e.key === 'Escape' && isOpen) {
      e.preventDefault();
      e.stopPropagation(); // keep the surrounding modal open
      closePanel();
      controlRef.current?.focus();
    }
  }

  const total = daysInMonth(view.year, view.month0);
  const offset = firstWeekdayMonday(view.year, view.month0);
  const cells = [];
  for (let i = 0; i < offset; i += 1) cells.push(null);
  for (let d = 1; d <= total; d += 1) cells.push(d);

  const today = todayDateOnly();

  return (
    <div
      className={[styles.wrap, className].filter(Boolean).join(' ')}
      ref={wrapRef}
      onKeyDown={handleKeyDown}
    >
      {label && <label className={styles.label} htmlFor={fieldId}>{label}</label>}

      <div className={styles.controlRow}>
        <button
          id={fieldId}
          ref={controlRef}
          type="button"
          className={[styles.control, isOpen && styles.controlOpen, error && styles.controlError]
            .filter(Boolean).join(' ')}
          aria-haspopup="dialog"
          aria-expanded={isOpen}
          aria-controls={isOpen ? dialogId : undefined}
          disabled={disabled}
          onClick={() => (isOpen ? closePanel() : openPanel())}
        >
          <span className={display ? styles.value : styles.placeholder}>
            {display || placeholder}
          </span>
          <span className={styles.icon} aria-hidden="true"><CalendarIcon /></span>
        </button>

        {value && !disabled && (
          <button
            type="button"
            className={styles.clearBtn}
            aria-label="Очистить дату"
            onClick={clear}
          >
            ×
          </button>
        )}
      </div>

      {error && <span className={styles.error} role="alert">{error}</span>}

      {isOpen && createPortal(
        <div
          ref={panelRef}
          id={dialogId}
          role="dialog"
          aria-modal="false"
          aria-label="Выбор даты"
          className={[styles.panel, panelPos.direction === 'up' ? styles.panelUp : styles.panelDown]
            .filter(Boolean).join(' ')}
          data-direction={panelPos.direction}
          style={{ top: panelPos.top, left: panelPos.left }}
          onKeyDown={handleKeyDown}
        >
          <div className={styles.panelHead}>
            <button
              type="button"
              className={styles.navBtn}
              aria-label="Предыдущий месяц"
              onClick={() => shiftMonth(-1)}
            >
              ‹
            </button>
            <span className={styles.monthLabel} aria-live="polite">
              {MONTHS[view.month0]} {view.year}
            </span>
            <button
              type="button"
              className={styles.navBtn}
              aria-label="Следующий месяц"
              onClick={() => shiftMonth(1)}
            >
              ›
            </button>
          </div>

          <div className={styles.weekRow} aria-hidden="true">
            {WEEKDAYS.map((w) => <span key={w} className={styles.weekday}>{w}</span>)}
          </div>

          <div className={styles.grid} role="grid">
            {cells.map((day, idx) => {
              if (day === null) return <span key={`e${idx}`} className={styles.empty} />;
              const dv = partsToDateOnly(view.year, view.month0, day);
              const isSelected = dv === value;
              const isToday = dv === today;
              const isDisabled = (min && dv < min) || (max && dv > max);
              return (
                <button
                  key={dv}
                  type="button"
                  className={[
                    styles.day,
                    isSelected && styles.daySelected,
                    isToday && !isSelected && styles.dayToday,
                  ].filter(Boolean).join(' ')}
                  aria-pressed={isSelected}
                  disabled={isDisabled}
                  onClick={() => selectDay(day)}
                >
                  {day}
                </button>
              );
            })}
          </div>

          <div className={styles.panelFoot}>
            <button type="button" className={styles.footBtn} onClick={clear}>
              Очистить
            </button>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
