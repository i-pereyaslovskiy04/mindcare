import { useCallback, useEffect, useRef, useState } from 'react';
import { getStudentVerifications } from '../../../api/studentVerification.api';
import { correctedPage } from '../../../shared/lib/pagination';

const PAGE_SIZE = 20;

/**
 * Очередь заявок на проверку для supervisor (ADR-029): ТОЛЬКО pending, без
 * поиска и фильтров (их нет намеренно — страница является очередью), серверная
 * пагинация по 20, порядок backend — FIFO (submitted_at ASC, id ASC). Номер
 * билета в списке не приходит.
 *
 * Контракт: { items, loading, pageLoading, error, total, page, setPage,
 * pageSize, refetch }.
 *
 * Строки привязаны к странице, для которой они получены (loadedPage): `page`
 * меняется сразу, а ответ приходит позже, поэтому пока loadedPage !== page,
 * `items` пуст и pageLoading=true — строки прежней страницы не выдаются за
 * строки новой и не доступны для открытия. Перезагрузка ТОЙ ЖЕ страницы
 * (refetch после решения) строк не скрывает. `loading` — идёт ли запрос;
 * pageLoading — нет ли ещё данных для текущей страницы. Ошибка принадлежит
 * странице, на которой возникла.
 *
 * Если страница опустела (решение, конкурентное решение другим супервизором),
 * хук сам переходит на существующую (shared/lib/pagination.correctedPage);
 * ответы устаревших запросов отбрасываются.
 * enabled=false — запросов нет (режим «под именем»: backend ответил бы 403).
 */
export default function useStudentVerifications(enabled = true) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loadedPage, setLoadedPage] = useState(null);
  const [loading, setLoading] = useState(Boolean(enabled));
  const [failure, setFailure] = useState(null);       // { page, message }
  const [page, setPage] = useState(1);

  const requestId = useRef(0);

  const fetchList = useCallback(async (p) => {
    const id = ++requestId.current;
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setFailure(null);
    let movedPage = false;
    try {
      const data = await getStudentVerifications({
        page: p, size: PAGE_SIZE, status: 'pending',
      });
      if (id !== requestId.current) return;
      const nextItems = Array.isArray(data?.items) ? data.items : [];
      const nextTotal = data?.total ?? 0;
      const target = correctedPage(p, PAGE_SIZE, nextItems.length, nextTotal);
      if (target !== p) {
        // Страница опустела: total запоминаем (пагинация), строк для p нет.
        // Ранее загруженные строки устарели (очередь изменилась) — сбрасываем
        // привязку, чтобы они не показались на целевой странице до её ответа.
        // Загрузка продолжается на существующей странице.
        movedPage = true;
        setTotal(nextTotal);
        setLoadedPage(null);
        setPage(target);
        return;
      }
      setItems(nextItems);
      setTotal(nextTotal);
      setLoadedPage(p);
    } catch (err) {
      if (id !== requestId.current) return;
      setFailure({ page: p, message: err?.message || 'Не удалось загрузить заявки' });
    } finally {
      if (id === requestId.current && !movedPage) setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    fetchList(page);
  }, [page, fetchList]);

  useEffect(() => () => { requestId.current += 1; }, []);

  const refetch = useCallback(() => fetchList(page), [fetchList, page]);

  const error = failure && failure.page === page ? failure.message : null;
  const pageReady = loadedPage === page;

  return {
    items: pageReady ? items : [],
    loading,
    pageLoading: enabled && !pageReady && !error,
    error,
    total,
    page,
    setPage,
    refetch,
    pageSize: PAGE_SIZE,
  };
}
