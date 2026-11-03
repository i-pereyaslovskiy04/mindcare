import { useCallback, useEffect, useRef, useState } from 'react';
import {
  deleteMyArticle, getMyArticle, getMyArticles, publishMyArticle, submitMyArticle,
} from '../../../api/articles.api';
import { ARTICLE_STATUS_LABELS } from '../lib/articleStatus';

export const MY_ARTICLES_PAGE_SIZE = 10;

const FALLBACK = 'Не удалось выполнить действие. Проверьте соединение и повторите попытку.';

function actionMessage(err) {
  if (err?.status === 409) {
    const current = err?.body?.current_status;
    return current
      ? `Действие недоступно: материал в статусе «${ARTICLE_STATUS_LABELS[current] || current}». Список обновлён.`
      : 'Действие недоступно в текущем статусе. Список обновлён.';
  }
  if (err?.status === 404) return 'Материал не найден. Список обновлён.';
  return FALLBACK;
}

/**
 * Свои статьи автора (ADR-034): список со статусами модерации, удаление и
 * переход к публикации — психолог отправляет на проверку (submit), супервизор
 * публикует сам (publish; Дополнение 2026-10-28). role выбирает API автора. Страницы догружаются («Показать ещё»), фильтр по
 * статусу — серверный. После действия и при 409/404 список перечитывается с
 * первой страницы (статус мог смениться у проверяющего). Повторное действие
 * во время запроса игнорируется (ref-lock). Загрузка статьи для правки —
 * loadForEdit(uuid) (полный текст нужен форме).
 */
export default function useMyArticles({ pageSize = MY_ARTICLES_PAGE_SIZE, role = 'psychologist' } = {}) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatusRaw] = useState('');
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
    getMyArticles({ page, size: pageSize, status: status || undefined }, role)
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
      .catch((err) => {
        if (id === reqId.current) setError(err);
      })
      .finally(() => {
        if (id === reqId.current) setLoading(false);
      });
  }, [page, pageSize, status, reloadKey, role]);

  const reload = useCallback(() => {
    setPage(1);
    setReloadKey(k => k + 1);
  }, []);

  const setStatus = useCallback((value) => {
    setStatusRaw(value || '');
    setPage(1);
    setItems([]);
  }, []);

  const loadMore = useCallback(() => setPage(p => p + 1), []);

  const run = useCallback(async (uuid, action) => {
    if (lock.current) return false;
    lock.current = true;
    setPendingUuid(uuid);
    setActionError(null);
    try {
      await action(uuid);
      reload();
      return true;
    } catch (err) {
      setActionError({ uuid, message: actionMessage(err) });
      if (err?.status === 409 || err?.status === 404) reload();
      return false;
    } finally {
      lock.current = false;
      setPendingUuid(null);
    }
  }, [reload]);

  const submit = useCallback((uuid) => run(uuid, submitMyArticle), [run]);
  const publish = useCallback((uuid) => run(uuid, publishMyArticle), [run]);
  const remove = useCallback((uuid) => run(uuid, (id) => deleteMyArticle(id, role)), [run, role]);
  const loadForEdit = useCallback((uuid) => getMyArticle(uuid, role), [role]);
  const clearActionError = useCallback(() => setActionError(null), []);

  return {
    items, total, loading, error,
    status, setStatus,
    hasMore: items.length < total,
    loadMore, reload,
    submit, publish, remove, loadForEdit,
    pendingUuid, actionError, clearActionError,
  };
}
