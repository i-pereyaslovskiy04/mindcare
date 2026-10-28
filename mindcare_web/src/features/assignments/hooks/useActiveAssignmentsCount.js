import { useEffect, useRef, useState } from 'react';
import { getMyAssignmentsSummary } from '../../../api/assignments.api';
import { subscribeAssignmentsChanged } from '../lib/assignmentEvents';

export const ASSIGNMENTS_POLL_MS = 30000;

function isTabVisible() {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden';
}

/**
 * Число доступных для выполнения заданий клиента (summary.open_count) — для
 * бейджа пункта меню «Задания психолога».
 *
 * «Доступные» — active при строго активном сопровождении: задания завершённых
 * сопровождений сюда не входят. Паттерн usePendingVerificationsCount: один
 * экземпляр на layout, загрузка при монтировании, опрос раз в 30 с только при
 * видимой вкладке, обновление при возврате на вкладку и после выполнения
 * задания (шина assignmentEvents); устаревший ответ отбрасывается.
 *
 * null — число неизвестно (ещё не загружено, ошибка первой загрузки,
 * enabled=false): ошибка не подменяет неизвестное значение нулём.
 * enabled=false (выход, impersonation, нет роли student) — запросов нет.
 */
export default function useActiveAssignmentsCount(enabled, userKey) {
  const [count, setCount] = useState(null);
  const requestId = useRef(0);

  useEffect(() => {
    if (!enabled) {
      requestId.current += 1;
      setCount(null);
      return undefined;
    }

    let alive = true;
    setCount(null);

    async function load() {
      const id = ++requestId.current;
      try {
        const data = await getMyAssignmentsSummary();
        if (!alive || id !== requestId.current) return;
        const value = Number(data?.open_count);
        if (Number.isInteger(value) && value >= 0) setCount(value);
      } catch {
        /* сеть/сервер — оставляем последнее известное значение */
      }
    }

    function onVisibility() {
      if (isTabVisible()) load();
    }

    load();
    const timer = setInterval(() => { if (isTabVisible()) load(); }, ASSIGNMENTS_POLL_MS);
    document.addEventListener('visibilitychange', onVisibility);
    const unsubscribe = subscribeAssignmentsChanged(load);

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
