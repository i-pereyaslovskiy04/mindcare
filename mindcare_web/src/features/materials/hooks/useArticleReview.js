import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getReviewArticle, getReviewArticles, publishReviewArticle, returnReviewArticle,
} from '../../../api/articles.api';
import { notifyReviewQueueChanged } from '../../moderation/lib/reviewQueueEvents';

export const REVIEW_PAGE_SIZE = 20;

const FALLBACK = 'Не удалось выполнить действие. Проверьте соединение и повторите попытку.';

function actionMessage(err) {
  if (err?.status === 409) return 'Материал уже не на проверке - решение принял другой проверяющий. Очередь обновлена.';
  if (err?.status === 404) return 'Материал больше не доступен для проверки. Очередь обновлена.';
  return FALLBACK;
}

/**
 * Очередь модерации статей психологов (ADR-034; supervisor/admin): статьи на
 * проверке, предпросмотр, публикация и возврат на доработку с комментарием.
 * После решения и при 409/404 очередь перечитывается, бейдж меню обновляется
 * сразу (reviewQueueEvents). Повторное действие во время запроса игнорируется
 * (ref-lock).
 */
export default function useArticleReview({ pageSize = REVIEW_PAGE_SIZE } = {}) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [pendingUuid, setPendingUuid] = useState(null);
  const [actionError, setActionError] = useState(null);   // { uuid, message }
  const reqId = useRef(0);
  const lock = useRef(false);

  useEffect(() => {
    const id = ++reqId.current;
    setLoading(true);
    setError(null);
    getReviewArticles({ page, size: pageSize })
      .then((data) => {
        if (id !== reqId.current) return;
        const fresh = Array.isArray(data?.items) ? data.items : [];
        setItems(prev => {
          if (page === 1) return fresh;
          const seen = new Set(prev.map(i => i.uuid));
          return [...prev, ...fresh.filter(i => !seen.has(i.uuid))];
        });
        setTotal(Number(data?.total) || 0);
      })
      .catch((err) => { if (id === reqId.current) setError(err); })
      .finally(() => { if (id === reqId.current) setLoading(false); });
  }, [page, pageSize, reloadKey]);

  const reload = useCallback(() => {
    setPage(1);
    setReloadKey(k => k + 1);
  }, []);

  const run = useCallback(async (uuid, action) => {
    if (lock.current) return false;
    lock.current = true;
    setPendingUuid(uuid);
    setActionError(null);
    try {
      await action();
      reload();
      notifyReviewQueueChanged();
      return true;
    } catch (err) {
      setActionError({ uuid, message: actionMessage(err) });
      if (err?.status === 409 || err?.status === 404) {
        reload();
        notifyReviewQueueChanged();
      }
      return false;
    } finally {
      lock.current = false;
      setPendingUuid(null);
    }
  }, [reload]);

  const publish = useCallback((uuid) => run(uuid, () => publishReviewArticle(uuid)), [run]);
  const sendBack = useCallback(
    (uuid, comment) => run(uuid, () => returnReviewArticle(uuid, comment)), [run],
  );
  const loadPreview = useCallback((uuid) => getReviewArticle(uuid), []);

  return {
    items, total, loading, error,
    hasMore: items.length < total,
    loadMore: useCallback(() => setPage(p => p + 1), []),
    reload, publish, sendBack, loadPreview,
    pendingUuid, actionError,
  };
}
