import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import Icon from '../../Icon/Icon';
import { computeActionsMenuPosition } from '../../../shared/lib/actionsMenuPosition';
import styles from './ActionsMenu.module.css';

const MENU_FALLBACK_SIZE = { width: 180, height: 120 };

/**
 * Меню «Другие действия» (кнопка ⋮ + всплывающий список). Получает уже
 * отфильтрованный фичей список: о ролях, правах и API ничего не знает.
 *
 * items: [{ id, label, onSelect, tone?: 'danger' | 'success', disabled? }].
 * Пустой список — меню не рендерится.
 *
 * Меню — в portal с position: fixed, поэтому не обрезается контейнером
 * таблицы. Клавиатура: Enter/Space/↓ на кнопке открывают меню и ставят фокус
 * на первый доступный пункт; ↑/↓/Home/End — по пунктам (недоступные
 * пропускаются); Escape закрывает и возвращает фокус на кнопку; Tab закрывает
 * и ведёт фокус дальше от кнопки. При выборе пункта фокус сначала
 * возвращается на кнопку, затем вызывается onSelect — диалог, открытый
 * действием, после закрытия вернёт фокус туда же.
 */
export default function ActionsMenu({ triggerLabel, items, className }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null);
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const menuId = useId();

  const enabledItems = useCallback(() => (
    menuRef.current ? [...menuRef.current.querySelectorAll('[role="menuitem"]:not(:disabled)')] : []
  ), []);

  const close = useCallback((returnFocus) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return;
    const menuRect = menuRef.current?.getBoundingClientRect();
    setPosition(computeActionsMenuPosition(
      triggerRef.current.getBoundingClientRect(),
      {
        width: menuRect?.width || MENU_FALLBACK_SIZE.width,
        height: menuRect?.height || MENU_FALLBACK_SIZE.height,
      },
      { width: window.innerWidth, height: window.innerHeight },
    ));
  }, []);

  // Клик вне меню закрывает его (без возврата фокуса — пользователь ушёл).
  useEffect(() => {
    if (!open) return undefined;
    const onDocMouseDown = (e) => {
      if (triggerRef.current?.contains(e.target) || menuRef.current?.contains(e.target)) return;
      close(false);
    };
    document.addEventListener('mousedown', onDocMouseDown, true);
    return () => document.removeEventListener('mousedown', onDocMouseDown, true);
  }, [open, close]);

  useLayoutEffect(() => {
    if (!open) return undefined;
    updatePosition();
    enabledItems()[0]?.focus();
    window.addEventListener('resize', updatePosition);
    document.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      document.removeEventListener('scroll', updatePosition, true);
    };
  }, [open, updatePosition, enabledItems]);

  if (!items || items.length === 0) return null;

  const onTriggerKeyDown = (e) => {
    if (e.key === 'ArrowDown' && !open) {
      e.preventDefault();
      setOpen(true);
    }
  };

  const onMenuKeyDown = (e) => {
    const list = enabledItems();
    const index = list.indexOf(document.activeElement);
    const focusAt = (i) => list[(i + list.length) % list.length]?.focus();
    switch (e.key) {
      case 'ArrowDown': e.preventDefault(); focusAt(index + 1); break;
      case 'ArrowUp': e.preventDefault(); focusAt(index - 1); break;
      case 'Home': e.preventDefault(); focusAt(0); break;
      case 'End': e.preventDefault(); focusAt(list.length - 1); break;
      case 'Escape':
        e.preventDefault();
        e.stopPropagation();   // закрыть только меню, не диалог вокруг
        close(true);
        break;
      case 'Tab':
        // Фокус — на кнопку; штатный Tab уведёт его к следующему элементу.
        close(true);
        break;
      default:
    }
  };

  const select = (item) => {
    close(true);
    item.onSelect?.();
  };

  const menu = open ? createPortal(
    <div
      id={menuId}
      ref={menuRef}
      role="menu"
      aria-label={triggerLabel}
      className={styles.menu}
      data-placement={position?.placement || 'down'}
      style={{ top: position?.top ?? 0, left: position?.left ?? 0 }}
      onKeyDown={onMenuKeyDown}
    >
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="menuitem"
          tabIndex={-1}
          disabled={item.disabled}
          className={[styles.item, item.tone ? styles[item.tone] : ''].filter(Boolean).join(' ')}
          onClick={() => select(item)}
        >
          {item.label}
        </button>
      ))}
    </div>,
    document.body,
  ) : null;

  return (
    <>
      <button
        type="button"
        ref={triggerRef}
        className={[styles.trigger, className].filter(Boolean).join(' ')}
        aria-label={triggerLabel}
        title={triggerLabel}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={onTriggerKeyDown}
      >
        <Icon name="more-vertical" size={16} />
      </button>
      {menu}
    </>
  );
}
