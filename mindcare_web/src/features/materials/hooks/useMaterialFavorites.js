import { useCallback, useEffect, useRef, useState } from 'react';
import { addFavorite, getFavoriteIds, removeFavorite } from '../../../api/materialFavorites.api';

const LIMIT_TEXT = 'В избранном уже максимум материалов — уберите ненужные.';
const UNAVAILABLE_TEXT = 'Материал недоступен — его сняли с публикации.';
const FALLBACK_TEXT = 'Не удалось сохранить избранное. Проверьте соединение и повторите попытку.';

/**
 * Серверное избранное (ADR-034): какие материалы отмечены и переключение.
 *
 * Без оптимистичного успеха: отметка меняется только по ответу сервера;
 * пока запрос идёт, кнопка этой карточки заблокирована (pendingId), повторное
 * нажатие игнорируется. После изменения вызывается onChanged (например,
 * перезагрузка списка «Только избранное»).
 *
 * enabled=false — запросов нет (impersonation, публичный сайт).
 */
export default function useMaterialFavorites({ enabled = true, onChanged } = {}) {
  const [ids, setIds] = useState(() => new Set());
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [pendingId, setPendingId] = useState(null);
  const [actionError, setActionError] = useState(null);
  const lock = useRef(false);
  const onChangedRef = useRef(onChanged);
  onChangedRef.current = onChanged;
  const reqId = useRef(0);

  const reload = useCallback(() => {
    const id = ++reqId.current;
    setLoadError(null);
    return getFavoriteIds().then(
      (data) => {
        if (id !== reqId.current) return;
        setIds(new Set(Array.isArray(data?.uuids) ? data.uuids : []));
        setLoaded(true);
      },
      (err) => {
        if (id !== reqId.current) return;
        setLoadError(err);
      },
    );
  }, []);

  useEffect(() => {
    if (!enabled) {
      reqId.current += 1;
      setIds(new Set());
      setLoaded(false);
      return;
    }
    reload();
  }, [enabled, reload]);

  const toggle = useCallback(async (item) => {
    if (!enabled || lock.current) return false;
    lock.current = true;
    const uuid = item.id;
    const wasFavorite = ids.has(uuid);
    setPendingId(uuid);
    setActionError(null);
    try {
      if (wasFavorite) await removeFavorite(uuid);
      else await addFavorite(uuid);
      setIds(prev => {
        const next = new Set(prev);
        if (wasFavorite) next.delete(uuid); else next.add(uuid);
        return next;
      });
      onChangedRef.current?.();
      return true;
    } catch (err) {
      const code = err?.body?.code || err?.code;
      if (err?.status === 409 && code === 'favorites_limit') setActionError(LIMIT_TEXT);
      else if (err?.status === 404) setActionError(UNAVAILABLE_TEXT);
      else setActionError(FALLBACK_TEXT);
      return false;
    } finally {
      lock.current = false;
      setPendingId(null);
    }
  }, [enabled, ids]);

  const isFavorite = useCallback((uuid) => ids.has(uuid), [ids]);

  return {
    isFavorite,
    toggle,
    count: ids.size,
    loaded,
    loadError,
    pendingId,
    actionError,
    reload,
  };
}
