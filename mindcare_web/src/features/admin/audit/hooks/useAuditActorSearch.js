import { useCallback, useEffect, useRef, useState } from 'react';
import { useDebounce } from '../../../../hooks/useDebounce';
import { getUsers } from '../../../../api/users.api';
import { maskEmail } from '../lib/auditFormatters';

/** Ниже этого порога поиск не запускается — иначе первая же буква тянет пол-БД. */
export const MIN_TERM_LENGTH = 2;

const PAGE_SIZE = 10;

/**
 * Из ответа admin users API берём ТОЛЬКО безопасную проекцию, и делаем это
 * сразу — до попадания в state. Внутренний `id` и полный email в состоянии
 * страницы журнала не хранятся вообще: страница нигде не показывает полных
 * адресов, а идентичность человека адресуется UUID'ом.
 */
function toSafeActor(item) {
  return {
    uuid: item.uuid,
    fullName: item.full_name,
    emailMasked: maskEmail(item.email),
    isDeleted: Boolean(item.deleted_at),
  };
}

/**
 * Поиск участника для точного фильтра `actor_uuid`.
 *
 * Удалённые аккаунты включены осознанно: в журналах постоянно фигурируют
 * пользователи, которых уже удалили, и без них фильтр по участнику для таких
 * строк не собрать.
 *
 * Строка поиска нигде не сохраняется — ни в URL, ни в storage.
 */
export function useAuditActorSearch() {
  const [term, setTerm] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const latest = useRef(0);

  const debounced = useDebounce(term, 300);

  /**
   * Инкремент `latest` здесь обязателен: без него ответ по старой строке,
   * пришедший уже после очистки, вернул бы результаты в пустой список.
   */
  const reset = useCallback(() => {
    latest.current += 1;
    setTerm('');
    setResults([]);
    setError(null);
    setLoading(false);
  }, []);

  useEffect(() => {
    const trimmed = debounced.trim();

    if (trimmed.length < MIN_TERM_LENGTH) {
      latest.current += 1;
      setResults([]);
      setError(null);
      setLoading(false);
      return undefined;
    }

    let cancelled = false;
    const reqId = latest.current + 1;
    latest.current = reqId;

    setLoading(true);
    setError(null);

    getUsers({ page: 1, size: PAGE_SIZE, search: trimmed, include_deleted: true })
      .then((data) => {
        if (cancelled || latest.current !== reqId) return;
        setResults((data?.items ?? []).map(toSafeActor));
      })
      .catch((err) => {
        if (cancelled || latest.current !== reqId) return;
        setResults([]);
        setError(err.message);
      })
      .finally(() => {
        if (cancelled || latest.current !== reqId) return;
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [debounced]);

  return { term, setTerm, results, loading, error, reset };
}
