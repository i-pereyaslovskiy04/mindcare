/**
 * Лёгкая шина «очередь модерации изменилась» (материалы и тесты) — по образцу
 * features/studentVerification/lib/verificationEvents.js.
 *
 * Страница модерации сообщает о решении, и бейджи меню проверяющего
 * обновляются сразу, не дожидаясь 30-секундного тика опроса.
 */

export const REVIEW_QUEUE_CHANGED_EVENT = 'mindcare:review-queue-changed';

export function notifyReviewQueueChanged() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(REVIEW_QUEUE_CHANGED_EVENT));
  }
}

/** Подписка; возвращает функцию отписки. */
export function subscribeReviewQueueChanged(callback) {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener(REVIEW_QUEUE_CHANGED_EVENT, callback);
  return () => window.removeEventListener(REVIEW_QUEUE_CHANGED_EVENT, callback);
}
