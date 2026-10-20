import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getStudentVerification,
  getStudentVerificationHistory,
} from '../../../api/studentVerification.api';

export const HISTORY_PAGE_SIZE = 10;

function mergeHistory(prev, next) {
  // Страховка от дублей (keyset на backend и так их не даёт).
  const seen = new Set(prev.map((item) => item.uuid));
  return prev.concat(next.filter((item) => !seen.has(item.uuid)));
}

/**
 * Карточка заявки для supervisor — содержит ПОЛНЫЙ номер билета (backend
 * пишет аудит чтения; при сбое аудита — 503 без номера) и первую порцию
 * истории подтверждения пользователя (все его заявки от новых к старым,
 * включая текущую; причины прежних отказов — тоже под аудитом).
 *
 * «Показать ещё» — loadMoreHistory(): следующая порция по курсору
 * next_cursor; ответ для другой карточки или устаревший — отбрасывается.
 *
 * Контракт: { data, loading, error, refetch, history, hasMoreHistory,
 * historyLoading, historyError, loadMoreHistory }.
 */
export default function useStudentVerificationCard(uuid) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(Boolean(uuid));
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);
  const latestRequest = useRef(0);
  const latestHistoryRequest = useRef(0);

  const refetch = useCallback(() => {
    const requestId = latestRequest.current + 1;
    latestRequest.current = requestId;
    latestHistoryRequest.current += 1;          // порции старой карточки — мимо
    const isLatest = () => latestRequest.current === requestId;
    setData(null);
    setHistory([]);
    setCursor(null);
    setHistoryLoading(false);
    setHistoryError(null);
    if (!uuid) {
      setLoading(false);
      setError(null);
      return Promise.resolve();
    }
    setLoading(true);
    setError(null);
    return getStudentVerification(uuid)
      .then((response) => {
        if (!isLatest()) return;
        setData(response);
        const first = response?.history;
        setHistory(Array.isArray(first?.items) ? first.items : []);
        setCursor(first?.has_more ? first.next_cursor ?? null : null);
      })
      .catch((err) => { if (isLatest()) setError(err); })
      .finally(() => { if (isLatest()) setLoading(false); });
  }, [uuid]);

  const loadMoreHistory = useCallback(() => {
    if (!uuid || !cursor) return Promise.resolve();
    const requestId = latestHistoryRequest.current + 1;
    latestHistoryRequest.current = requestId;
    const isLatest = () => latestHistoryRequest.current === requestId;
    setHistoryLoading(true);
    setHistoryError(null);
    return getStudentVerificationHistory(uuid, { before: cursor, size: HISTORY_PAGE_SIZE })
      .then((portion) => {
        if (!isLatest()) return;
        setHistory((prev) => mergeHistory(prev, Array.isArray(portion?.items) ? portion.items : []));
        setCursor(portion?.has_more ? portion.next_cursor ?? null : null);
      })
      .catch((err) => { if (isLatest()) setHistoryError(err); })
      .finally(() => { if (isLatest()) setHistoryLoading(false); });
  }, [uuid, cursor]);

  useEffect(() => {
    refetch();
    return () => {
      latestRequest.current += 1;
      latestHistoryRequest.current += 1;
    };
  }, [refetch]);

  return {
    data,
    loading,
    error,
    refetch,
    history,
    hasMoreHistory: Boolean(cursor),
    historyLoading,
    historyError,
    loadMoreHistory,
  };
}
