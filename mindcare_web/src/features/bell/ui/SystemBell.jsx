/**
 * SystemBell — колокольчик шапки кабинета (только student и psychologist).
 *
 * Слой представления над системной беседой «Психология ДонГУ», а не отдельная
 * система уведомлений: badge — её unread_count, панель — до 5 непрочитанных
 * сообщений. Открытие панели ничего не отмечает прочитанным: пункт и
 * «Показать все» ведут в Messenger на системную беседу (`?system=1`), и уже
 * там срабатывает существующий mark-read.
 *
 * Панель немодальная (disclosure): без focus trap, Tab идёт по DOM-порядку
 * (панель рендерится сразу после кнопки), уход фокуса за пределы, Escape и
 * клик снаружи её закрывают. position: fixed — overflow: hidden layout'а её не
 * обрезает, поэтому портал не нужен; позиция — общий useAnchoredPanel.
 */
import { useCallback, useEffect, useId } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../../../components/Icon/Icon';
import useAnchoredPanel from '../../../hooks/useAnchoredPanel';
import { useSystemBell } from '../hooks/useSystemBell';
import {
  BELL_EMPTY_TEXT,
  BELL_ERROR_TEXT,
  BELL_SHOW_ALL,
  BELL_TITLE,
  badgeText,
  bellLabel,
  formatBellTime,
  hasBell,
  systemChatHref,
} from '../lib/bellView';
import styles from './SystemBell.module.css';

// Отступ панели от краёв окна; ширину задаёт CSS (на <=600px — почти экран).
const PANEL_GUTTER = 16;

export default function SystemBell({ cabinetRole, triggerClassName }) {
  const panelId = useId();
  const titleId = useId();
  const { isOpen, setIsOpen, close, calcPos, pos, wrapRef, triggerRef } = useAnchoredPanel(
    panelId,
    0,
    { gutter: PANEL_GUTTER },
  );
  const { unreadCount, items, itemsStatus, loadItems, resetItems } = useSystemBell(
    hasBell(cabinetRole),
  );

  const href = systemChatHref(cabinetRole);
  const badge = badgeText(unreadCount);

  // Список — при открытии и при изменении числа непрочитанных, пока панель
  // открыта; закрытая панель списка не держит.
  useEffect(() => {
    if (isOpen) loadItems();
    else resetItems();
  }, [isOpen, unreadCount, loadItems, resetItems]);

  const closeAndFocus = useCallback(() => {
    close();
    triggerRef.current?.focus();
  }, [close, triggerRef]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') closeAndFocus();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, closeAndFocus]);

  const toggle = () => {
    if (isOpen) {
      close();
      return;
    }
    calcPos();
    setIsOpen(true);
  };

  // Фокус ушёл из кнопки и панели (Tab дальше по шапке) — панель закрывается.
  // relatedTarget = null (клик по пустому месту) обрабатывает клик снаружи.
  const onBlur = (e) => {
    if (isOpen && e.relatedTarget && !wrapRef.current?.contains(e.relatedTarget)) close();
  };

  let body;
  if (itemsStatus === 'error') {
    body = <p className={styles.state} role="status">{BELL_ERROR_TEXT}</p>;
  } else if (items.length > 0) {
    body = (
      <ul className={styles.items}>
        {items.map((item) => (
          <li key={item.id}>
            <Link to={href} className={styles.item} onClick={close}>
              <span className={styles.itemText}>{item.text}</span>
              <time className={styles.itemTime} dateTime={item.createdAt}>
                {formatBellTime(item.createdAt)}
              </time>
            </Link>
          </li>
        ))}
      </ul>
    );
  } else if (itemsStatus === 'ready') {
    body = <p className={styles.state} role="status">{BELL_EMPTY_TEXT}</p>;
  } else {
    body = <p className={styles.state} role="status">Загрузка…</p>;
  }

  return (
    <div className={styles.wrap} ref={wrapRef} onBlur={onBlur}>
      <button
        ref={triggerRef}
        type="button"
        className={[triggerClassName, styles.trigger, isOpen && styles.triggerOpen]
          .filter(Boolean)
          .join(' ')}
        aria-label={bellLabel(unreadCount)}
        title={BELL_TITLE}
        aria-expanded={isOpen}
        aria-controls={isOpen ? panelId : undefined}
        onClick={toggle}
      >
        <Icon name="bell" size={16} />
        {badge && (
          <span className={styles.badge} aria-hidden="true">{badge}</span>
        )}
      </button>

      {isOpen && (
        <section
          id={panelId}
          className={styles.panel}
          aria-labelledby={titleId}
          style={{ top: pos.top, left: pos.left }}
        >
          <h2 id={titleId} className={styles.title}>{BELL_TITLE}</h2>
          {body}
          <Link to={href} className={styles.showAll} onClick={close}>{BELL_SHOW_ALL}</Link>
        </section>
      )}
    </div>
  );
}
