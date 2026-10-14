/**
 * CabinetDrawer — мобильное меню кабинета (<=600px) для CabinetLayout и
 * AdminLayout: backdrop + aside role="dialog" + кнопка «Закрыть меню».
 * Содержимое (brand, пользователь, навигация, footer) передаёт layout —
 * это та же разметка, что в его sidebar, отдельной мобильной навигации нет.
 *
 * Фокус:
 *   - при открытии — на «Закрыть меню» (первый контрол drawer'а);
 *   - Tab / Shift+Tab ходят по кругу внутри drawer'а — клавиатура не уходит
 *     на страницу под ним;
 *   - Escape и клик по backdrop закрывают; после закрытия (любым способом,
 *     включая переход по пункту меню) фокус возвращается на returnFocusRef
 *     (кнопку-hamburger в шапке).
 *
 * Рендерит фрагмент: aside остаётся прямым потомком оболочки кабинета
 * ([data-cabinet-shell] > aside — правила режима для слабовидящих).
 */

import { useEffect, useRef } from 'react';
import styles from './CabinetDrawer.module.css';

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function CabinetDrawer({
  open,
  onClose,
  returnFocusRef,
  id,
  label = 'Меню кабинета',
  className,
  children,
}) {
  const drawerRef = useRef(null);
  const closeRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const trigger = returnFocusRef?.current;
    closeRef.current?.focus();
    return () => {
      trigger?.focus();
    };
  }, [open, returnFocusRef]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const onKeyDown = (e) => {
    if (e.key !== 'Tab') return;
    const items = Array.from(drawerRef.current?.querySelectorAll(FOCUSABLE) ?? []);
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  return (
    <>
      <div className={styles.backdrop} onClick={onClose} aria-hidden="true" />
      <aside
        id={id}
        ref={drawerRef}
        className={[styles.drawer, className].filter(Boolean).join(' ')}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        onKeyDown={onKeyDown}
      >
        <button
          ref={closeRef}
          className={styles.close}
          type="button"
          aria-label="Закрыть меню"
          onClick={onClose}
        >
          <span aria-hidden="true">✕</span>
        </button>
        {children}
      </aside>
    </>
  );
}
