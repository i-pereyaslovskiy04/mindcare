/**
 * Лёгкая шина «задания изменились» — без глобального store
 * (по образцу features/studentVerification/lib/verificationEvents.js).
 *
 * Страница заданий сообщает об успешном выполнении, и бейдж меню клиента
 * обновляется сразу, не дожидаясь 30-секундного тика опроса.
 */

export const ASSIGNMENTS_CHANGED_EVENT = 'mindcare:assignments-changed';

export function notifyAssignmentsChanged() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(ASSIGNMENTS_CHANGED_EVENT));
  }
}

/** Подписка; возвращает функцию отписки. */
export function subscribeAssignmentsChanged(callback) {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener(ASSIGNMENTS_CHANGED_EVENT, callback);
  return () => window.removeEventListener(ASSIGNMENTS_CHANGED_EVENT, callback);
}
