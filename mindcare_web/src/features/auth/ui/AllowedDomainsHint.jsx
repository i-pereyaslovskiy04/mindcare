import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import Icon from '../../../components/Icon/Icon';
import styles from './AuthModal.module.css';

export const DOMAINS_HINT_ID = 'r-email-domains';
export const DOMAIN_ERROR_ID = 'r-email-domain-error';
const TOOLTIP_ID = 'r-email-domains-tooltip';

// Выше Modal (2000), как выпадающий список shared Select.
const TOOLTIP_Z_INDEX = 2100;
const GAP = 6;
const VIEWPORT_MARGIN = 8;
// Пауза перед закрытием по уходу мыши: указатель успевает перейти с кнопки
// на сам tooltip через зазор (WCAG 1.4.13 — содержимое можно навести).
const HOVER_CLOSE_DELAY_MS = 120;

/** Домен адреса так же, как его берёт backend: strip + lower, часть после последнего «@». */
export function emailDomainOf(email) {
  const normalized = (email || '').trim().toLowerCase();
  const at = normalized.lastIndexOf('@');
  return at < 0 ? '' : normalized.slice(at + 1);
}

/** Домена нет в загруженном списке. Только для подсказки: допуск решает backend. */
export function isDomainUnsupported(email, domains) {
  const domain = emailDomainOf(email);
  return Boolean(domain) && !domains.some((d) => d.toLowerCase() === domain);
}

/**
 * Разрешённые домены под полем Email: одна компактная строка (подсказка или
 * ошибка «Этот домен не поддерживается.») с info-кнопкой слева — её место не
 * меняется при смене текста. Список — в floating tooltip: портал в body,
 * position: fixed поверх AuthModal (её overflow не обрезает), в потоке формы
 * его нет, высота формы не меняется.
 *
 * Открытие: hover мышью (закрывается при уходе), фокус с клавиатуры
 * (закрывается на blur), click/tap — закрепляет; повторный click/tap, клик
 * снаружи и Escape закрывают. Escape перехватывается в capture-фазе, чтобы не
 * закрыть AuthModal. Tooltip смонтирован всегда (hidden, пока закрыт): список
 * входит в описание кнопки (aria-describedby) и для скринридера.
 *
 * domains — из useAllowedEmailDomains (ответ backend); пустой — блока нет.
 * children — ошибка формата email, под строкой подсказки.
 */
export default function AllowedDomainsHint({ domains, unsupported, children }) {
  // null — закрыт; 'hover' | 'focus' | 'click' — чем открыт (от этого зависит,
  // что его закрывает).
  const [mode, setMode] = useState(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const triggerRef = useRef(null);
  const tooltipRef = useRef(null);
  const pointerFocus = useRef(false);
  const closeTimer = useRef(null);
  const open = mode !== null;

  const cancelClose = () => { clearTimeout(closeTimer.current); };
  const close = useCallback(() => { clearTimeout(closeTimer.current); setMode(null); }, []);
  const scheduleHoverClose = () => {
    cancelClose();
    closeTimer.current = setTimeout(() => {
      setMode((current) => (current === 'hover' ? null : current));
    }, HOVER_CLOSE_DELAY_MS);
  };

  useEffect(() => () => clearTimeout(closeTimer.current), []);

  const place = useCallback(() => {
    const trigger = triggerRef.current;
    const tip = tooltipRef.current;
    if (!trigger || !tip) return;
    const r = trigger.getBoundingClientRect();
    const { offsetWidth: w, offsetHeight: h } = tip;
    let top = r.bottom + GAP;
    if (top + h > window.innerHeight - VIEWPORT_MARGIN && r.top - GAP - h >= VIEWPORT_MARGIN) {
      top = r.top - GAP - h;
    }
    const left = Math.max(
      VIEWPORT_MARGIN,
      Math.min(r.left - VIEWPORT_MARGIN, window.innerWidth - w - VIEWPORT_MARGIN),
    );
    setPos({ top, left });
  }, []);

  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (e) => {
      if (e.key !== 'Escape') return;
      // Первый Escape закрывает tooltip, а не AuthModal (её обработчик — на
      // document в фазе всплытия). Фокус остаётся на кнопке.
      e.stopPropagation();
      close();
    };
    const onPointerDown = (e) => {
      if (triggerRef.current?.contains(e.target) || tooltipRef.current?.contains(e.target)) return;
      close();
    };
    document.addEventListener('keydown', onKeyDown, true);
    document.addEventListener('mousedown', onPointerDown, true);
    document.addEventListener('touchstart', onPointerDown, true);
    window.addEventListener('scroll', place, true);
    window.addEventListener('resize', place);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      document.removeEventListener('mousedown', onPointerDown, true);
      document.removeEventListener('touchstart', onPointerDown, true);
      window.removeEventListener('scroll', place, true);
      window.removeEventListener('resize', place);
    };
  }, [open, close, place]);

  if (!domains.length) return children ?? null;

  const handlers = {
    onMouseEnter: () => {
      cancelClose();
      setMode((current) => current ?? 'hover');
    },
    onMouseLeave: () => {
      if (mode === 'hover') scheduleHoverClose();
    },
    // Фокус от мыши/тача — не клавиатурный: открытием управляют hover и click.
    onMouseDown: () => { pointerFocus.current = true; },
    onTouchStart: () => { pointerFocus.current = true; },
    onFocus: () => {
      if (pointerFocus.current) {
        pointerFocus.current = false;
        return;
      }
      setMode((current) => current ?? 'focus');
    },
    onBlur: () => {
      pointerFocus.current = false;
      if (mode === 'focus' || mode === 'click') close();
    },
    // Click/tap закрепляет открытый hover/focus и закрывает закреплённый.
    // На touch первый tap даёт эмулированный mouseenter (hover) и click → закреплён;
    // второй tap → закрыт.
    onClick: () => {
      cancelClose();
      setMode((current) => (current === 'click' ? null : 'click'));
    },
  };

  return (
    <div className={styles.domains}>
      <div className={`${styles.authNote} ${styles.domainsHint} ${unsupported ? styles.domainsHintError : ''}`}>
        <button
          ref={triggerRef}
          type="button"
          className={styles.domainsInfo}
          aria-label="Показать разрешённые домены"
          aria-expanded={open}
          aria-controls={TOOLTIP_ID}
          aria-describedby={TOOLTIP_ID}
          {...handlers}
        >
          <Icon name="info" size={15} />
        </button>
        {unsupported ? (
          <span id={DOMAIN_ERROR_ID} role="alert">Этот домен не поддерживается.</span>
        ) : (
          <span id={DOMAINS_HINT_ID}>Почта должна быть на разрешённом домене</span>
        )}
      </div>
      {children}
      {createPortal(
        <div
          ref={tooltipRef}
          id={TOOLTIP_ID}
          role="tooltip"
          className={styles.domainsTooltip}
          hidden={!open}
          style={{ top: pos.top, left: pos.left, zIndex: TOOLTIP_Z_INDEX }}
          onMouseEnter={cancelClose}
          onMouseLeave={() => { if (mode === 'hover') scheduleHoverClose(); }}
          // Нажатие внутри не уводит фокус с кнопки (иначе blur закрыл бы tooltip).
          onMouseDown={(e) => e.preventDefault()}
        >
          <span className={styles.domainsTitle}>Разрешённые домены</span>
          {/* Неразрывный пробел перед «·»: точка не переносится в начало строки. */}
          <span className={styles.domainsList}>
            {domains.map((d) => `@${d}`).join(' · ')}
          </span>
        </div>,
        document.body,
      )}
    </div>
  );
}
