/**
 * Лёгкая шина «сообщения изменились» — без Redux/глобального store.
 *
 * Используется, чтобы layout-badge раздела «Сообщения» обновлялся СРАЗУ после
 * mark-read / send / прихода новых, не дожидаясь 30-секундного poll-тика.
 */

export const MESSAGES_UPDATED_EVENT = 'mindcare:messages-updated';

export function notifyMessagesUpdated() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(MESSAGES_UPDATED_EVENT));
  }
}

/** Подписка; возвращает функцию отписки. */
export function subscribeMessagesUpdated(callback) {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener(MESSAGES_UPDATED_EVENT, callback);
  return () => window.removeEventListener(MESSAGES_UPDATED_EVENT, callback);
}
