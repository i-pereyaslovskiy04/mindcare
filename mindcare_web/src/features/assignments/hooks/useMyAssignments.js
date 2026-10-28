import { useCallback, useEffect, useRef, useState } from 'react';
import {
  completeMyAssignment, getMyAssignments, getMyAssignmentsSummary,
} from '../../../api/assignments.api';
import { notifyAssignmentsChanged } from '../lib/assignmentEvents';
import useKeysetList from './useKeysetList';

export const MY_ASSIGNMENTS_PAGE_SIZE = 20;
export const SUMMARY_POLL_MS = 30000;

const COMPLETE_ERRORS = {
  assignment_engagement_inactive:
    'Сопровождение завершено — задание доступно только для просмотра.',
  assignment_finalized: 'Задание уже отменено психологом.',
  assignment_not_available: 'Задание недоступно.',
};
const COMPLETE_FALLBACK = 'Не удалось сохранить отметку. Проверьте соединение и повторите попытку.';
const AUDIT_UNAVAILABLE = 'Не удалось сохранить отметку. Повторите попытку позже.';

function isTabVisible() {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden';
}

/**
 * Задания клиента: «Активные» (view=open) и «История» (view=history), сводка
 * и отметка выполнения.
 *
 * Оба списка — keyset. Сбрасываются и грузятся с первой страницы:
 *   * после своего выполнения (успех или no-op);
 *   * после 409 (сопровождение закрыли / задание отменили) и 404.
 * Внешние изменения ловит опрос раз в 30 с (видимая вкладка, возврат на
 * вкладку): сводка + первая страница каждого списка. Сравнивается СОСТАВ
 * первой страницы (uuid, статус, доступность действия) и total/has_more, а не
 * только счётчики сводки: при передаче или реактивации сопровождения набор
 * заданий меняется при тех же числах. Изменившийся список заменяется свежей
 * первой страницей; проба, начатая до сброса или до своего действия,
 * отбрасывается (generation списка + номер пробы).
 * Оптимистичного успеха нет: статус меняется только по ответу сервера и
 * перезагрузке; ошибка сохранения показывается отдельно (actionError).
 * Повторное нажатие во время запроса игнорируется (pendingUuid + ref-lock).
 */
export default function useMyAssignments({ enabled = true, pageSize = MY_ASSIGNMENTS_PAGE_SIZE } = {}) {
  const fetchOpen = useCallback(
    ({ before }) => getMyAssignments({ view: 'open', before, size: pageSize }), [pageSize],
  );
  const fetchHistory = useCallback(
    ({ before }) => getMyAssignments({ view: 'history', before, size: pageSize }), [pageSize],
  );
  const open = useKeysetList(fetchOpen, { enabled });
  const history = useKeysetList(fetchHistory, { enabled });

  const [summary, setSummary] = useState(null);
  const [pendingUuid, setPendingUuid] = useState(null);
  const [actionError, setActionError] = useState(null);
  const lockRef = useRef(false);
  const summaryReq = useRef(0);
  const probeReq = useRef(0);

  const resetOpen = open.reset;
  const resetHistory = history.reset;
  const resetLists = useCallback(() => {
    probeReq.current += 1;          // проба в полёте устарела
    resetOpen();
    resetHistory();
  }, [resetOpen, resetHistory]);

  const loadSummary = useCallback(async () => {
    const id = ++summaryReq.current;
    try {
      const data = await getMyAssignmentsSummary();
      if (id === summaryReq.current) setSummary(data);
    } catch {
      /* сводка необязательна для работы со списками — оставляем прежнюю */
    }
  }, []);

  const { getGeneration: openGeneration, applyFirstPage: applyOpen } = open;
  const { getGeneration: historyGeneration, applyFirstPage: applyHistory } = history;

  // Проба состава: сводка и первые страницы обоих списков. Каждый список
  // заменяется, только если его состав изменился и после начала пробы не было
  // сброса (generation). Сбой пробы ничего не меняет.
  const probe = useCallback(async () => {
    const id = ++probeReq.current;
    const genOpen = openGeneration();
    const genHistory = historyGeneration();
    loadSummary();
    let pages;
    try {
      pages = await Promise.all([fetchOpen({ before: undefined }), fetchHistory({ before: undefined })]);
    } catch {
      return;
    }
    if (id !== probeReq.current) return;
    applyOpen(pages[0], genOpen);
    applyHistory(pages[1], genHistory);
  }, [openGeneration, historyGeneration, applyOpen, applyHistory, fetchOpen, fetchHistory, loadSummary]);

  useEffect(() => {
    if (!enabled) return undefined;
    loadSummary();
    const timer = setInterval(() => { if (isTabVisible()) probe(); }, SUMMARY_POLL_MS);
    const onVisibility = () => { if (isTabVisible()) probe(); };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      summaryReq.current += 1;
      probeReq.current += 1;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [enabled, loadSummary, probe]);

  const refetch = useCallback(() => {
    setActionError(null);
    resetLists();
    loadSummary();
  }, [resetLists, loadSummary]);

  const complete = useCallback(async (uuid) => {
    if (lockRef.current) return false;
    lockRef.current = true;
    setPendingUuid(uuid);
    setActionError(null);
    try {
      await completeMyAssignment(uuid);
      notifyAssignmentsChanged();
      resetLists();
      loadSummary();
      return true;
    } catch (err) {
      const code = err?.body?.code || err?.code;
      if (err?.status === 503) {
        setActionError({ uuid, message: AUDIT_UNAVAILABLE });
      } else if (err?.status === 409 || err?.status === 404) {
        setActionError({ uuid, message: COMPLETE_ERRORS[code] || COMPLETE_FALLBACK });
        // Состав изменился извне — перечитываем оба списка.
        resetLists();
        loadSummary();
      } else {
        setActionError({ uuid, message: COMPLETE_FALLBACK });
      }
      return false;
    } finally {
      lockRef.current = false;
      setPendingUuid(null);
    }
  }, [resetLists, loadSummary]);

  const clearActionError = useCallback(() => setActionError(null), []);

  return {
    open,
    history,
    summary,
    refetch,
    complete,
    pendingUuid,
    actionError,
    clearActionError,
  };
}
