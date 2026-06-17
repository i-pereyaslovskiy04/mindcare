import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import Icon from '../../../components/Icon/Icon';
import { computeActionsMenuPosition } from './actionsMenuPosition';
import styles from './MessageActionsMenu.module.css';

const MENU_FALLBACK_SIZE = { width: 150, height: 80 };

/**
 * Компактное kebab-меню действий над своим сообщением (Stage 31y).
 *
 * Заменяет отдельную кнопку-карандаш: одна кнопка «…», в меню — «Редактировать»
 * и «Удалить» (danger). Feature-specific (внутри features/chat): глобального
 * shared-меню в проекте нет, плодить его ради одного места не нужно.
 *
 * Доступность: кнопка-триггер фокусируема (открытие с клавиатуры через Enter/
 * Space — нативно для button); Escape и клик вне закрывают меню; пункты —
 * обычные button. На touch меню открывается по tap (не зависит от hover).
 */
export default function MessageActionsMenu({ onEdit, onDelete, triggerClassName = '' }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null);
  const wrapRef = useRef(null);
  const triggerRef = useRef(null);
  const menuRef = useRef(null);

  const close = useCallback(() => setOpen(false), []);

  const updatePosition = useCallback(() => {
    if (!triggerRef.current || typeof window === 'undefined') return;
    const anchorRect = triggerRef.current.getBoundingClientRect();
    const menuRect = menuRef.current?.getBoundingClientRect();
    const menuSize = {
      width: menuRect?.width || MENU_FALLBACK_SIZE.width,
      height: menuRect?.height || MENU_FALLBACK_SIZE.height,
    };

    setPosition(computeActionsMenuPosition(
      anchorRect,
      menuSize,
      { width: window.innerWidth, height: window.innerHeight },
    ));
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      if (wrapRef.current?.contains(e.target) || menuRef.current?.contains(e.target)) return;
      close();
    };
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();   // не закрывать диалог/тред — только меню
        close();
      }
    };
    document.addEventListener('mousedown', onDocClick, true);
    document.addEventListener('keydown', onKey, true);
    return () => {
      document.removeEventListener('mousedown', onDocClick, true);
      document.removeEventListener('keydown', onKey, true);
    };
  }, [open, close]);

  useLayoutEffect(() => {
    if (!open) return undefined;
    updatePosition();
    window.addEventListener('resize', updatePosition);
    document.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      document.removeEventListener('scroll', updatePosition, true);
    };
  }, [open, updatePosition]);

  const handleEdit = () => {
    close();
    onEdit?.();
  };

  const handleDelete = () => {
    close();
    onDelete?.();
  };

  const menu = open && typeof document !== 'undefined' ? createPortal(
    <div
      className={styles.menu}
      role="menu"
      ref={menuRef}
      data-placement={position?.placement || 'down'}
      style={{ top: position?.top ?? 0, left: position?.left ?? 0 }}
    >
      <button
        type="button"
        role="menuitem"
        className={styles.item}
        onClick={handleEdit}
      >
        Редактировать
      </button>
      <button
        type="button"
        role="menuitem"
        className={`${styles.item} ${styles.itemDanger}`}
        onClick={handleDelete}
      >
        Удалить
      </button>
    </div>,
    document.body,
  ) : null;

  return (
    <div className={styles.wrap} ref={wrapRef}>
      <button
        type="button"
        ref={triggerRef}
        className={`${styles.trigger} ${triggerClassName}`.trim()}
        aria-label="Действия с сообщением"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="more-vertical" size={16} />
      </button>

      {menu}
    </div>
  );
}
