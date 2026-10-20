import { useEffect, useRef, useState } from 'react';
import { getPendingVerificationsCount } from '../../../api/studentVerification.api';
import { subscribeVerificationsChanged } from '../lib/verificationEvents';

export const PENDING_POLL_MS = 30000;

function isTabVisible() {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden';
}

/**
 * Число заявок, ожидающих проверки, — для бейджа пункта меню супервизора.
 *
 * Один экземпляр на layout (desktop sidebar и mobile drawer рендерят одну
 * разметку → один таймер). Загрузка при монтировании, опрос раз в 30 с только
 * при видимой вкладке, обновление при возврате на вкладку и после решения по
 * заявке (шина verificationEvents). Ответ устаревшего запроса отбрасывается.
 *
 * Возвращает null, пока число неизвестно (ещё не загружено, ошибка первой
 * загрузки, enabled=false), иначе — последнее успешно полученное число:
 * ошибка не подменяет неизвестное значение нулём. enabled=false (выход,
 * impersonation, нет роли supervisor) — запросов нет; unmount (смена
 * кабинета, выход) останавливает опрос.
 */
export default function usePendingVerificationsCount(enabled, userKey) {
  const [count, setCount] = useState(null);
  const requestId = useRef(0);

  useEffect(() => {
    if (!enabled) {
      requestId.current += 1;
      setCount(null);
      return undefined;
    }

    let alive = true;
    // Другой пользователь — значение прежнего неизвестно для нового.
    setCount(null);

    async function load() {
      const id = ++requestId.current;
      try {
        const data = await getPendingVerificationsCount();
        if (!alive || id !== requestId.current) return;
        const value = Number(data?.count);
        if (Number.isInteger(value) && value >= 0) setCount(value);
      } catch {
        /* сеть/сервер — оставляем последнее известное значение */
      }
    }

    function tick() {
      if (isTabVisible()) load();
    }

    function onVisibility() {
      if (isTabVisible()) load();
    }

    load();
    const timer = setInterval(tick, PENDING_POLL_MS);
    document.addEventListener('visibilitychange', onVisibility);
    const unsubscribe = subscribeVerificationsChanged(load);

    return () => {
      alive = false;
      requestId.current += 1;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibility);
      unsubscribe();
    };
  }, [enabled, userKey]);

  return count;
}
