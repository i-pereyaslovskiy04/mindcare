import { useCallback, useEffect, useRef, useState } from 'react';

const INITIAL = {
  items: [],
  total: 0,
  hasMore: false,
  nextCursor: null,
  loading: true,
  loadingMore: false,
  error: null,          // ошибка первой страницы или фатальная ошибка догрузки (Error с .status)
  loadMoreError: null,  // нефатальная ошибка догрузки: загруженное остаётся на месте
};

/**
 * Отпечаток первой страницы: состав (uuid), статус и доступность действий
 * каждого элемента, а также total/has_more всей выборки. Совпадение счётчиков
 * сводки не означает совпадения состава (передача и реактивация сопровождения
 * заменяют набор заданий при тех же числах) — поэтому сравнивается сам состав.
 */
export function pageSignature(data) {
  const items = Array.isArray(data?.items) ? data.items : [];
  const rows = items.map(i => [
    i.uuid, i.status, i.can_complete ?? '', i.can_cancel ?? '', i.engagement_active ?? '',
  ].join(':'));
  return `${rows.join('|')}#total=${Number(data?.total) || 0}#more=${Boolean(data?.has_more)}`;
}

function stateFromFirstPage(data) {
  return {
    items: Array.isArray(data?.items) ? data.items : [],
    total: Number(data?.total) || 0,
    hasMore: Boolean(data?.has_more),
    nextCursor: data?.next_cursor ?? null,
    loading: false,
    loadingMore: false,
    error: null,
    loadMoreError: null,
  };
}

/**
 * Keyset-список заданий: первая страница, догрузка по курсору, сброс и
 * применение свежей первой страницы («проба» при опросе).
 *
 * fetchPage({ before }) → { items, has_more, next_cursor, total }.
 *
 * Сброс (reset) и применение изменившейся пробы увеличивают generation:
 * ответы запросов, начатых до этого (в т.ч. догрузки), отбрасываются и не
 * смешиваются с новым списком. Курсор сервера не зависит от того, остался ли
 * его элемент в выборке, поэтому переход задания между open/history не даёт
 * пропусков; новые элементы выше курсора подхватываются сбросом или пробой.
 * Дубли по uuid отбрасываются как страховка.
 *
 * isFatalLoadMoreError(err) → true — догрузка показала, что список больше
 * недоступен (например, 404 у психолога после закрытия сопровождения): данные
 * очищаются, ошибка становится ошибкой списка. Иначе — loadMoreError, данные
 * остаются, догрузку можно повторить.
 *
 * enabled=false — запросов нет. resetKey — смена владельца списка (например
 * uuid клиента): прежние данные пропадают сразу.
 */
export default function useKeysetList(
  fetchPage,
  { enabled = true, resetKey = null, isFatalLoadMoreError = null } = {},
) {
  const [state, setState] = useState(INITIAL);
  const generation = useRef(0);
  const cursorRef = useRef(null);
  const loadingMoreRef = useRef(false);
  const snapshotRef = useRef(null);
  const fetchRef = useRef(fetchPage);
  fetchRef.current = fetchPage;
  const fatalRef = useRef(isFatalLoadMoreError);
  fatalRef.current = isFatalLoadMoreError;

  const reset = useCallback(() => {
    const gen = ++generation.current;
    cursorRef.current = null;
    loadingMoreRef.current = false;
    setState(prev => ({ ...prev, loading: true, error: null, loadMoreError: null, loadingMore: false }));
    return fetchRef.current({ before: undefined }).then(
      (data) => {
        if (gen !== generation.current) return;
        cursorRef.current = data?.next_cursor ?? null;
        snapshotRef.current = pageSignature(data);
        setState(stateFromFirstPage(data));
      },
      (err) => {
        if (gen !== generation.current) return;
        cursorRef.current = null;
        snapshotRef.current = null;
        setState({ ...INITIAL, loading: false, error: err });
      },
    );
  }, []);

  const loadMore = useCallback(() => {
    const before = cursorRef.current;
    if (!before || loadingMoreRef.current) return Promise.resolve();
    const gen = generation.current;
    loadingMoreRef.current = true;
    setState(prev => ({ ...prev, loadingMore: true, loadMoreError: null }));
    return fetchRef.current({ before }).then(
      (data) => {
        if (gen !== generation.current) return;
        loadingMoreRef.current = false;
        cursorRef.current = data?.next_cursor ?? null;
        setState(prev => {
          const seen = new Set(prev.items.map(i => i.uuid));
          const fresh = (Array.isArray(data?.items) ? data.items : []).filter(i => !seen.has(i.uuid));
          return {
            ...prev,
            items: [...prev.items, ...fresh],
            total: Number(data?.total) || prev.total,
            hasMore: Boolean(data?.has_more),
            nextCursor: data?.next_cursor ?? null,
            loadingMore: false,
          };
        });
      },
      (err) => {
        if (gen !== generation.current) return;
        loadingMoreRef.current = false;
        if (fatalRef.current?.(err)) {
          generation.current += 1;
          cursorRef.current = null;
          snapshotRef.current = null;
          setState({ ...INITIAL, loading: false, error: err });
          return;
        }
        setState(prev => ({ ...prev, loadingMore: false, loadMoreError: err }));
      },
    );
  }, []);

  /** Текущее поколение списка — фиксируется перед пробой. */
  const getGeneration = useCallback(() => generation.current, []);

  /**
   * Применяет свежую первую страницу, полученную пробой, начатой при
   * поколении gen. Устаревшая проба (после неё был сброс/применение) и проба
   * с тем же составом ничего не меняют. Иначе список заменяется первой
   * страницей (догруженные страницы и догрузка в полёте отбрасываются).
   * Возвращает true, если список заменён.
   */
  const applyFirstPage = useCallback((data, gen) => {
    if (gen !== generation.current) return false;
    const signature = pageSignature(data);
    if (signature === snapshotRef.current) return false;
    generation.current += 1;
    loadingMoreRef.current = false;
    cursorRef.current = data?.next_cursor ?? null;
    snapshotRef.current = signature;
    setState(stateFromFirstPage(data));
    return true;
  }, []);

  useEffect(() => {
    if (!enabled) {
      generation.current += 1;
      cursorRef.current = null;
      snapshotRef.current = null;
      setState({ ...INITIAL, loading: false });
      return undefined;
    }
    setState(INITIAL);
    snapshotRef.current = null;
    reset();
    return () => { generation.current += 1; };
  }, [enabled, resetKey, reset]);

  return { ...state, loadMore, reset, getGeneration, applyFirstPage };
}
