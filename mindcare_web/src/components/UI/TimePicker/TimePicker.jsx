import {
  useState, useRef, useEffect, useLayoutEffect, useCallback, useId, useMemo,
} from 'react';
import { createPortal } from 'react-dom';
import styles from './TimePicker.module.css';

const ClockIcon = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.4" />
    <path d="M8 4.8V8l2.2 1.6" stroke="currentColor" strokeWidth="1.4"
      strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const pad = (n) => String(n).padStart(2, '0');

/**
 * Нормализует свободный ввод 'H:M' / 'HH:MM' в 'HH:MM', либо null если ввод
 * не является валидным временем (часы 0–23, минуты 0–59).
 */
export function parseTime(str) {
  if (typeof str !== 'string') return null;
  const m = /^(\d{1,2}):(\d{1,2})$/.exec(str.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (h < 0 || h > 23 || mi < 0 || mi > 59) return null;
  return `${pad(h)}:${pad(mi)}`;
}

/**
 * Выбор времени 'HH:MM' без нативного <input type="time">.
 *
 * Пользователь может: (1) ввести время вручную в текстовом поле (валидируется
 * по HH:MM, невалидный ввод не применяется и подсвечивается ошибкой на blur);
 * (2) выбрать часы и минуты в компактном popover-гриде (две колонки), а не в
 * одном длинном выпадающем списке.
 *
 * Controlled: value 'HH:MM' | '', onChange(next: 'HH:MM' | '').
 * Props: value, onChange, label?, placeholder?, disabled?, error?, minuteStep=15,
 *        id?, className?
 */
export default function TimePicker({
  value = '',
  onChange,
  label,
  placeholder = 'чч:мм',
  disabled = false,
  error,
  minuteStep = 15,
  id,
  className,
}) {
  const reactId = useId();
  const fieldId = id || `timepicker-${reactId}`;
  const dialogId = `${fieldId}-dialog`;

  const [isOpen, setIsOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const [localError, setLocalError] = useState(false);
  const [panelPos, setPanelPos] = useState({ top: 0, left: 0, minWidth: 0 });

  const wrapRef = useRef(null);
  const inputRef = useRef(null);
  const toggleRef = useRef(null);
  const panelRef = useRef(null);
  const focusedRef = useRef(false);

  // Внешнее изменение value пересинхронизирует поле, пока в нём нет фокуса.
  useEffect(() => {
    if (!focusedRef.current) {
      setDraft(value);
      setLocalError(false);
    }
  }, [value]);

  const { hh, mm } = useMemo(() => {
    const norm = parseTime(value);
    if (!norm) return { hh: '', mm: '' };
    const [h, m] = norm.split(':');
    return { hh: h, mm: m };
  }, [value]);

  const hours = useMemo(
    () => Array.from({ length: 24 }, (_, i) => pad(i)),
    [],
  );
  const minutes = useMemo(() => {
    const step = minuteStep > 0 ? minuteStep : 15;
    const out = [];
    for (let m = 0; m < 60; m += step) out.push(pad(m));
    return out;
  }, [minuteStep]);

  const calcPos = useCallback(() => {
    if (!wrapRef.current) return;
    const r = wrapRef.current.getBoundingClientRect();
    const panelW = panelRef.current ? panelRef.current.offsetWidth : 180;
    const left = Math.max(
      12, Math.min(r.left, window.innerWidth - panelW - 12),
    );
    setPanelPos({ top: r.bottom + 4, left, minWidth: r.width });
  }, []);

  const openPanel = useCallback(() => {
    if (disabled) return;
    calcPos();
    setIsOpen(true);
  }, [disabled, calcPos]);

  const closePanel = useCallback(() => setIsOpen(false), []);

  function commit(next) {
    onChange?.(next);
  }

  function handleInputChange(e) {
    const raw = e.target.value;
    setDraft(raw);
    setLocalError(false);
    if (raw.trim() === '') {
      commit('');
      return;
    }
    const norm = parseTime(raw);
    if (norm) commit(norm);
  }

  function handleBlur() {
    focusedRef.current = false;
    const raw = draft.trim();
    if (raw === '') {
      setDraft('');
      setLocalError(false);
      commit('');
      return;
    }
    const norm = parseTime(raw);
    if (norm) {
      setDraft(norm);
      setLocalError(false);
      commit(norm);
    } else {
      // Невалидный ввод не применяем: показываем ошибку и откатываем к value.
      setLocalError(true);
      setDraft(value);
    }
  }

  function pickHour(h) {
    commit(`${h}:${mm || '00'}`);
    setLocalError(false);
  }
  function pickMinute(m) {
    commit(`${hh || '00'}:${m}`);
    setLocalError(false);
  }

  // Закрытие по клику вне (capture ловит и портальную панель).
  useEffect(() => {
    if (!isOpen) return undefined;
    const onOutside = (e) => {
      if (
        !wrapRef.current?.contains(e.target)
        && !panelRef.current?.contains(e.target)
      ) {
        closePanel();
      }
    };
    document.addEventListener('mousedown', onOutside, true);
    return () => document.removeEventListener('mousedown', onOutside, true);
  }, [isOpen, closePanel]);

  // Репозиция при скролле/ресайзе.
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
      e.stopPropagation(); // не закрывать окружающую модалку
      closePanel();
      inputRef.current?.focus();
    }
  }

  const showError = error || (localError ? 'Неверное время (чч:мм)' : null);

  return (
    <div
      className={[styles.wrap, className].filter(Boolean).join(' ')}
      ref={wrapRef}
      onKeyDown={handleKeyDown}
    >
      {label && (
        <label className={styles.label} htmlFor={fieldId}>{label}</label>
      )}

      <div
        className={[
          styles.control,
          isOpen && styles.controlOpen,
          showError && styles.controlError,
        ].filter(Boolean).join(' ')}
      >
        <input
          id={fieldId}
          ref={inputRef}
          type="text"
          inputMode="numeric"
          autoComplete="off"
          className={styles.input}
          value={draft}
          placeholder={placeholder}
          disabled={disabled}
          aria-invalid={showError ? true : undefined}
          onFocus={() => { focusedRef.current = true; }}
          onChange={handleInputChange}
          onBlur={handleBlur}
        />
        <button
          ref={toggleRef}
          type="button"
          className={styles.toggle}
          aria-haspopup="dialog"
          aria-expanded={isOpen}
          aria-controls={isOpen ? dialogId : undefined}
          aria-label="Выбрать время"
          disabled={disabled}
          tabIndex={-1}
          onClick={() => (isOpen ? closePanel() : openPanel())}
        >
          <ClockIcon />
        </button>
      </div>

      {showError && <span className={styles.error} role="alert">{showError}</span>}

      {isOpen && createPortal(
        <div
          ref={panelRef}
          id={dialogId}
          role="dialog"
          aria-modal="false"
          aria-label="Выбор времени"
          className={styles.panel}
          style={{ top: panelPos.top, left: panelPos.left }}
          onKeyDown={handleKeyDown}
        >
          <div className={styles.cols}>
            <div className={styles.col}>
              <div className={styles.colTitle}>Часы</div>
              <div className={styles.optList} role="listbox" aria-label="Часы">
                {hours.map((h) => (
                  <button
                    key={h}
                    type="button"
                    role="option"
                    aria-selected={h === hh}
                    className={[styles.opt, h === hh && styles.optActive]
                      .filter(Boolean).join(' ')}
                    onClick={() => pickHour(h)}
                  >
                    {h}
                  </button>
                ))}
              </div>
            </div>
            <div className={styles.col}>
              <div className={styles.colTitle}>Минуты</div>
              <div className={styles.optList} role="listbox" aria-label="Минуты">
                {minutes.map((m) => (
                  <button
                    key={m}
                    type="button"
                    role="option"
                    aria-selected={m === mm}
                    className={[styles.opt, m === mm && styles.optActive]
                      .filter(Boolean).join(' ')}
                    onClick={() => pickMinute(m)}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className={styles.foot}>
            <button
              type="button"
              className={styles.footBtn}
              onClick={() => { closePanel(); inputRef.current?.focus(); }}
            >
              Готово
            </button>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
