import { useCallback, useEffect, useRef, useState } from 'react';
import { getStudentTestResults } from '../../../api/tests.api';

export const STAFF_RESULTS_PAGE_SIZE = 20;

const INITIAL = {
  items: [],
  total: 0,
  loading: true,
  loadingMore: false,
  error: null,          // ошибка первой страницы или потеря доступа (Error с .status)
  loadMoreError: null,  // нефатальная ошибка догрузки: загруженное остаётся
};

// 403/404 — доступа к результатам клиента нет (сопровождение завершено,
// передано, клиент отключён). Уже показанное очищается.
export const isAccessLost = (err) => err?.status === 404 || err?.status === 403;

/** Статус раздела по состоянию списка. */
export function resultsStatus(state) {
  if (state.error) return isAccessLost(state.error) ? 'unavailable' : 'error';
  if (state.loading && state.items.length === 0) return 'loading';
  return 'ready';
}

/**
 * Результаты психодиагностики клиента для staff (metadata, без баллов).
 *
 * Серверные страницы (page/size) с «Показать ещё»: следующая страница
 * дописывается с дедупом по uuid (новое прохождение сдвигает страницы).
 * Смена клиента или роли (studentUuid/activeRole) сразу очищает список;
 * ответы запросов прежнего поколения отбрасываются (generation). 403/404
 * догрузки — доступа больше нет: данные очищаются (status 'unavailable').
 * invalidate(err) — то же по сигналу извне (деталь/ответы получили 404).
 */
export default function useStaffTestResults(
  studentUuid, activeRole, { pageSize = STAFF_RESULTS_PAGE_SIZE } = {},
) {
  const [state, setState] = useState(INITIAL);
  const [reloadKey, setReloadKey] = useState(0);
  const generation = useRef(0);
  const pageRef = useRef(0);
  const loadingMoreRef = useRef(false);

  useEffect(() => {
    const gen = ++generation.current;
    pageRef.current = 0;
    loadingMoreRef.current = false;
    if (!studentUuid) {
      setState({ ...INITIAL, loading: false });
      return undefined;
    }
    setState(INITIAL);
    getStudentTestResults(studentUuid, activeRole, { page: 1, size: pageSize }).then(
      (data) => {
        if (gen !== generation.current) return;
        pageRef.current = 1;
        setState({
          ...INITIAL,
          items: Array.isArray(data?.items) ? data.items : [],
          total: Number(data?.total) || 0,
          loading: false,
        });
      },
      (err) => {
        if (gen !== generation.current) return;
        setState({ ...INITIAL, loading: false, error: err });
      },
    );
    return () => { generation.current += 1; };
  }, [studentUuid, activeRole, pageSize, reloadKey]);

  const loadMore = useCallback(() => {
    if (loadingMoreRef.current || !studentUuid) return Promise.resolve();
    const gen = generation.current;
    const nextPage = pageRef.current + 1;
    loadingMoreRef.current = true;
    setState(prev => ({ ...prev, loadingMore: true, loadMoreError: null }));
    return getStudentTestResults(studentUuid, activeRole, { page: nextPage, size: pageSize }).then(
      (data) => {
        if (gen !== generation.current) return;
        loadingMoreRef.current = false;
        pageRef.current = nextPage;
        setState(prev => {
          const seen = new Set(prev.items.map(i => i.uuid));
          const fresh = (Array.isArray(data?.items) ? data.items : []).filter(i => !seen.has(i.uuid));
          return {
            ...prev,
            items: [...prev.items, ...fresh],
            total: Number(data?.total) || prev.total,
            loadingMore: false,
          };
        });
      },
      (err) => {
        if (gen !== generation.current) return;
        loadingMoreRef.current = false;
        if (isAccessLost(err)) {
          generation.current += 1;
          setState({ ...INITIAL, loading: false, error: err });
          return;
        }
        setState(prev => ({ ...prev, loadingMore: false, loadMoreError: err }));
      },
    );
  }, [studentUuid, activeRole, pageSize]);

  /** Доступ потерян (сигнал детали/ответов): всё показанное очищается. */
  const invalidate = useCallback((err) => {
    generation.current += 1;
    loadingMoreRef.current = false;
    setState({ ...INITIAL, loading: false, error: err });
  }, []);

  const refetch = useCallback(() => setReloadKey(k => k + 1), []);

  return {
    ...state,
    hasMore: state.items.length < state.total,
    status: resultsStatus(state),
    loadMore,
    invalidate,
    refetch,
  };
}
