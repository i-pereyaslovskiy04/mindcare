import { useEffect, useRef, useState } from 'react';
import { getReviewArticlesPendingCount } from '../../../api/articles.api';
import { getTestsPendingCount } from '../../../api/tests.api';
import { subscribeReviewQueueChanged } from '../lib/reviewQueueEvents';

export const REVIEW_POLL_MS = 30000;

const UNKNOWN = { articles: null, tests: null };

function isTabVisible() {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden';
}

function parseCount(data) {
  const value = Number(data?.count);
  return Number.isInteger(value) && value >= 0 ? value : null;
}

/**
 * Число материалов и тестов, ожидающих модерации, — для бейджей меню
 * проверяющего (supervisor / admin). Паттерн usePendingVerificationsCount:
 * один экземпляр на layout, опрос раз в 30 с только при видимой вкладке,
 * обновление при возврате на вкладку и после решения (шина reviewQueueEvents),
 * устаревший ответ отбрасывается.
 *
 * Каждое значение — null, пока неизвестно (не загружено, ошибка первой
 * загрузки, enabled=false), иначе последнее успешно полученное: ошибка одного
 * счётчика не обнуляет его и не мешает другому.
 */
export default function useReviewQueueCounts(enabled, userKey) {
  const [counts, setCounts] = useState(UNKNOWN);
  const requestId = useRef(0);

  useEffect(() => {
    if (!enabled) {
      requestId.current += 1;
      setCounts(UNKNOWN);
      return undefined;
    }

    let alive = true;
    // Другой пользователь — значения прежнего неизвестны для нового.
    setCounts(UNKNOWN);

    function apply(id, key, data) {
      if (!alive || id !== requestId.current) return;
      const value = parseCount(data);
      if (value !== null) setCounts(prev => (prev[key] === value ? prev : { ...prev, [key]: value }));
    }

    function load() {
      const id = ++requestId.current;
      getReviewArticlesPendingCount().then(d => apply(id, 'articles', d), () => {});
      getTestsPendingCount().then(d => apply(id, 'tests', d), () => {});
    }

    function onTick() {
      if (isTabVisible()) load();
    }

    load();
    const timer = setInterval(onTick, REVIEW_POLL_MS);
    document.addEventListener('visibilitychange', onTick);
    const unsubscribe = subscribeReviewQueueChanged(load);

    return () => {
      alive = false;
      requestId.current += 1;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onTick);
      unsubscribe();
    };
  }, [enabled, userKey]);

  return counts;
}

/** Бейдж пункта меню: число (99+ при большом), доступная подпись — точное число. */
export function reviewBadge(count) {
  if (!(count > 0)) return {};
  return {
    badge: count > 99 ? '99+' : String(count),
    badgeLabel: `ожидают проверки: ${count}`,
  };
}
