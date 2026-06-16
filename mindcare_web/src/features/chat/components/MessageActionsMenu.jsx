import { useCallback, useEffect, useRef, useState } from 'react';
import Icon from '../../../components/Icon/Icon';
import styles from './MessageActionsMenu.module.css';

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
  const wrapRef = useRef(null);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      if (!wrapRef.current?.contains(e.target)) close();
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

  const handleEdit = () => {
    close();
    onEdit?.();
  };

  const handleDelete = () => {
    close();
    onDelete?.();
  };

  return (
    <div className={styles.wrap} ref={wrapRef}>
      <button
        type="button"
        className={`${styles.trigger} ${triggerClassName}`.trim()}
        aria-label="Действия с сообщением"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="more-vertical" size={16} />
      </button>

      {open && (
        <div className={styles.menu} role="menu">
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
        </div>
      )}
    </div>
  );
}
