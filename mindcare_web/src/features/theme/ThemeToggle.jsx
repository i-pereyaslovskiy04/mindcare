/**
 * ThemeToggle — переключатель темы для Navbar и topbar кабинета.
 *
 * Два варианта отображения:
 *   • обычный (Navbar, где есть место) — сегментированный режим
 *     (Светлая / Тёмная / Системная) + выпадающее меню выбора палитры;
 *   • compact (topbar кабинета и админки) — одна иконка-кнопка, режим и
 *     палитра живут внутри выпадающей панели. В шапке кабинета уже есть поиск,
 *     колокольчик, почта и выход: развёрнутый контрол ломал раскладку topbar на
 *     desktop и не помещался на мобильной ширине.
 *
 * Feature-specific контрол (обоснование): shared Select — форменное поле
 * с label/placeholder/error, в шапке избыточно; shared Toggle — только boolean.
 * Панель рендерится через портал с position: fixed — иначе её обрезает
 * overflow: hidden у CabinetLayout. Иконки — inline SVG на currentColor.
 * Вне ThemeProvider рендерится null (безопасно для изолированных тестов).
 */

import { useCallback, useContext, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ThemeContext } from './ThemeContext';
import styles from './ThemeToggle.module.css';

const SunIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx="8" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.4" />
    <path
      d="M8 1.2v1.8M8 13v1.8M1.2 8H3M13 8h1.8M3.2 3.2l1.3 1.3M11.5 11.5l1.3 1.3M12.8 3.2l-1.3 1.3M4.5 11.5l-1.3 1.3"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
    />
  </svg>
);

const MoonIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path
      d="M13.5 9.8A6 6 0 0 1 6.2 2.5a6 6 0 1 0 7.3 7.3z"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinejoin="round"
    />
  </svg>
);

const SystemIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <rect x="1.7" y="2.7" width="12.6" height="8.6" rx="1.3" stroke="currentColor" strokeWidth="1.4" />
    <path d="M5.5 14h5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

const PaletteIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path
      d="M8 1.6a6.4 6.4 0 0 0 0 12.8c.9 0 1.5-.7 1.5-1.4 0-.4-.2-.7-.4-1-.2-.2-.3-.5-.3-.8 0-.7.6-1.2 1.3-1.2h1.2A3.1 3.1 0 0 0 14.4 6.9C14.2 3.9 11.4 1.6 8 1.6z"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinejoin="round"
    />
    <circle cx="5.2" cy="6" r="0.9" fill="currentColor" />
    <circle cx="8" cy="4.6" r="0.9" fill="currentColor" />
    <circle cx="10.9" cy="6" r="0.9" fill="currentColor" />
  </svg>
);

const ChevronIcon = () => (
  <svg width="9" height="6" viewBox="0 0 10 6" fill="none" aria-hidden="true">
    <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const CheckIcon = () => (
  <svg width="9" height="7" viewBox="0 0 9 7" fill="none" aria-hidden="true">
    <path d="M1 3.5l2.5 2.5L8 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const MODE_OPTIONS = [
  { value: 'light', short: 'Светлая', label: 'Светлая тема', Icon: SunIcon },
  { value: 'dark', short: 'Тёмная', label: 'Тёмная тема', Icon: MoonIcon },
  {
    value: 'system',
    short: 'Системная',
    label: 'Системная тема (как в настройках устройства)',
    Icon: SystemIcon,
  },
];

const PALETTE_OPTIONS = [
  { value: 'coffee', short: 'Кофе', label: 'Кофейная палитра' },
  { value: 'nature', short: 'Природа', label: 'Палитра «Природное спокойствие»' },
  { value: 'classic', short: 'Классика', label: 'Классическая (академическая) палитра' },
  { value: 'hc', short: 'Контраст', label: 'Высококонтрастная тема (для слабовидящих)' },
];

/**
 * Панель, привязанная к кнопке-триггеру: позиция считается от неё и
 * пересчитывается на scroll/resize. Панель рендерится в портал, поэтому
 * закрытие по клику снаружи проверяет и триггер, и саму панель по id.
 */
function useAnchoredPanel(panelId, minPanelWidth) {
  const [isOpen, setIsOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0, minWidth: 0 });

  const wrapRef = useRef(null);
  const triggerRef = useRef(null);

  const calcPos = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const width = Math.max(r.width, minPanelWidth);
    const left = Math.max(12, Math.min(r.right - width, window.innerWidth - width - 12));
    setPos({ top: r.bottom + 6, left, minWidth: width });
  }, [minPanelWidth]);

  const close = useCallback(() => setIsOpen(false), []);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onOutside = (e) => {
      const panel = document.getElementById(panelId);
      if (!wrapRef.current?.contains(e.target) && !panel?.contains(e.target)) close();
    };
    const reposition = () => calcPos();
    document.addEventListener('mousedown', onOutside, true);
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
    return () => {
      document.removeEventListener('mousedown', onOutside, true);
      window.removeEventListener('scroll', reposition, true);
      window.removeEventListener('resize', reposition);
    };
  }, [isOpen, panelId, close, calcPos]);

  return { isOpen, setIsOpen, close, calcPos, pos, wrapRef, triggerRef };
}

/** Выпадающее меню выбора цветовой палитры. */
function PaletteMenu({ palette, setPalette }) {
  const [activeIndex, setActiveIndex] = useState(-1);
  const listboxId = useId();
  const { isOpen, setIsOpen, close: closePanel, calcPos, pos, wrapRef, triggerRef } =
    useAnchoredPanel(listboxId, 190);

  const selectedIndex = PALETTE_OPTIONS.findIndex((o) => o.value === palette);
  const selected = PALETTE_OPTIONS[selectedIndex] ?? PALETTE_OPTIONS[0];

  const open = useCallback(() => {
    calcPos();
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : 0);
    setIsOpen(true);
  }, [calcPos, selectedIndex, setIsOpen]);

  const close = useCallback(() => {
    closePanel();
    setActiveIndex(-1);
  }, [closePanel]);

  const choose = useCallback(
    (value) => {
      setPalette(value);
      close();
      triggerRef.current?.focus();
    },
    [setPalette, close, triggerRef],
  );

  const onKeyDown = (e) => {
    switch (e.key) {
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (!isOpen) open();
        else if (activeIndex >= 0) choose(PALETTE_OPTIONS[activeIndex].value);
        break;
      case 'Escape':
        if (isOpen) {
          e.preventDefault();
          e.stopPropagation();
          close();
        }
        break;
      case 'ArrowDown':
        e.preventDefault();
        if (!isOpen) open();
        else setActiveIndex((i) => Math.min(i + 1, PALETTE_OPTIONS.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        if (!isOpen) open();
        else setActiveIndex((i) => Math.max(i - 1, 0));
        break;
      case 'Tab':
        if (isOpen) close();
        break;
      default:
        break;
    }
  };

  return (
    <div className={styles.menuWrap} ref={wrapRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`${styles.trigger} ${isOpen ? styles.triggerOpen : ''}`}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={isOpen ? listboxId : undefined}
        aria-label={`Цветовая тема: ${selected.short}`}
        title={selected.label}
        onClick={() => (isOpen ? close() : open())}
        onKeyDown={onKeyDown}
      >
        <span className={styles.triggerIcon} aria-hidden="true">
          <PaletteIcon />
        </span>
        <span className={styles.triggerLabel}>{selected.short}</span>
        <span className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`} aria-hidden="true">
          <ChevronIcon />
        </span>
      </button>

      {isOpen &&
        createPortal(
          <ul
            id={listboxId}
            role="listbox"
            aria-label="Цветовая тема"
            className={styles.panel}
            style={{ top: pos.top, left: pos.left, minWidth: pos.minWidth }}
          >
            {PALETTE_OPTIONS.map((opt, idx) => {
              const isSelected = opt.value === palette;
              return (
                <li
                  key={opt.value}
                  role="option"
                  aria-selected={isSelected}
                  aria-label={opt.label}
                  className={[
                    styles.menuOption,
                    isSelected && styles.menuOptionSelected,
                    idx === activeIndex && styles.menuOptionActive,
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    choose(opt.value);
                  }}
                  onMouseEnter={() => setActiveIndex(idx)}
                >
                  <span className={styles.menuCheck} aria-hidden="true">
                    {isSelected && <CheckIcon />}
                  </span>
                  <span className={styles.menuLabel}>{opt.short}</span>
                </li>
              );
            })}
          </ul>,
          document.body,
        )}
    </div>
  );
}

/**
 * Compact-вариант: одна иконка-кнопка, режим и палитра — в выпадающей панели.
 * Используется в шапке кабинета/админки, где на развёрнутый контрол нет места.
 */
function CompactThemeMenu({ className, mode, setMode, resolvedMode, palette, setPalette }) {
  const panelId = useId();
  const { isOpen, setIsOpen, close, calcPos, pos, wrapRef, triggerRef } = useAnchoredPanel(
    panelId,
    230,
  );

  const open = useCallback(() => {
    calcPos();
    setIsOpen(true);
  }, [calcPos, setIsOpen]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      close();
      triggerRef.current?.focus();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, close, triggerRef]);

  const selectedPalette =
    PALETTE_OPTIONS.find((o) => o.value === palette) ?? PALETTE_OPTIONS[0];

  return (
    <div className={[styles.menuWrap, className].filter(Boolean).join(' ')} ref={wrapRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`${styles.iconTrigger} ${isOpen ? styles.iconTriggerOpen : ''}`}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        aria-controls={isOpen ? panelId : undefined}
        aria-label={`Оформление: ${selectedPalette.short}`}
        title="Оформление: тема и режим"
        onClick={() => (isOpen ? close() : open())}
      >
        <PaletteIcon />
      </button>

      {isOpen &&
        createPortal(
          <div
            id={panelId}
            role="dialog"
            aria-label="Оформление"
            className={styles.sheet}
            style={{ top: pos.top, left: pos.left, minWidth: pos.minWidth }}
          >
            <div className={styles.sheetTitle}>Режим</div>
            <div className={styles.sheetModes} role="group" aria-label="Режим темы оформления">
              {MODE_OPTIONS.map(({ value, short, label, Icon }) => {
                const isActive = mode === value;
                const title =
                  value === 'system'
                    ? `${label} — сейчас: ${resolvedMode === 'dark' ? 'тёмная' : 'светлая'}`
                    : label;
                return (
                  <button
                    key={value}
                    type="button"
                    className={`${styles.sheetMode} ${isActive ? styles.sheetModeActive : ''}`}
                    aria-pressed={isActive}
                    aria-label={title}
                    title={title}
                    onClick={() => setMode(value)}
                  >
                    <Icon />
                    <span>{short}</span>
                  </button>
                );
              })}
            </div>

            <div className={styles.sheetTitle}>Цветовая тема</div>
            <ul role="listbox" aria-label="Цветовая тема" className={styles.sheetList}>
              {PALETTE_OPTIONS.map((opt) => {
                const isSelected = opt.value === palette;
                return (
                  <li
                    key={opt.value}
                    role="option"
                    aria-selected={isSelected}
                    aria-label={opt.label}
                    className={[styles.menuOption, isSelected && styles.menuOptionSelected]
                      .filter(Boolean)
                      .join(' ')}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      setPalette(opt.value);
                    }}
                  >
                    <span className={styles.menuCheck} aria-hidden="true">
                      {isSelected && <CheckIcon />}
                    </span>
                    <span className={styles.menuLabel}>{opt.short}</span>
                  </li>
                );
              })}
            </ul>
          </div>,
          document.body,
        )}
    </div>
  );
}

/**
 * withPalette — показывать ли выбор палитры (по умолчанию да);
 * в тесных местах можно отключить и оставить только режим.
 * compact — одна иконка-кнопка вместо развёрнутого контрола (шапка кабинета).
 */
export default function ThemeToggle({ className, withPalette = true, compact = false }) {
  const ctx = useContext(ThemeContext);
  if (!ctx) return null;

  const { mode, setMode, resolvedMode, palette, setPalette } = ctx;

  if (compact) {
    return (
      <CompactThemeMenu
        className={className}
        mode={mode}
        setMode={setMode}
        resolvedMode={resolvedMode}
        palette={palette}
        setPalette={setPalette}
      />
    );
  }

  return (
    <div className={[styles.wrap, className].filter(Boolean).join(' ')}>
      <div className={styles.group} role="group" aria-label="Режим темы оформления">
        {MODE_OPTIONS.map(({ value, label, Icon }) => {
          const isActive = mode === value;
          const title =
            value === 'system'
              ? `${label} — сейчас: ${resolvedMode === 'dark' ? 'тёмная' : 'светлая'}`
              : label;
          return (
            <button
              key={value}
              type="button"
              className={`${styles.option} ${isActive ? styles.optionActive : ''}`}
              aria-pressed={isActive}
              aria-label={title}
              title={title}
              onClick={() => setMode(value)}
            >
              <Icon />
            </button>
          );
        })}
      </div>
      {withPalette && <PaletteMenu palette={palette} setPalette={setPalette} />}
    </div>
  );
}
