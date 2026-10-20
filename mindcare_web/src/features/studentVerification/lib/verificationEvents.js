/**
 * Лёгкая шина «очередь подтверждения изменилась» — без глобального store
 * (по образцу features/chat/lib/messagesEvents.js).
 *
 * Страница очереди сообщает о решении по заявке, и бейдж меню супервизора
 * обновляется сразу, не дожидаясь 30-секундного тика опроса.
 */

export const VERIFICATIONS_CHANGED_EVENT = 'mindcare:verifications-changed';

export function notifyVerificationsChanged() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(VERIFICATIONS_CHANGED_EVENT));
  }
}

/** Подписка; возвращает функцию отписки. */
export function subscribeVerificationsChanged(callback) {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener(VERIFICATIONS_CHANGED_EVENT, callback);
  return () => window.removeEventListener(VERIFICATIONS_CHANGED_EVENT, callback);
}
