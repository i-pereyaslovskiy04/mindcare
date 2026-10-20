import { useState, useEffect } from 'react';
import { useDebounce } from '../../../../hooks/useDebounce';
import { getUsers } from '../../../../api/users.api';
import { correctedPage } from '../../../../shared/lib/pagination';

/**
 * Параметры списка из галочки «Показать отключённых» (ADR-028) — только
 * существующие параметры API, смысл include_deleted не меняется:
 *   выключена → is_active=true (backend: is_active IS NOT FALSE AND
 *               deleted_at IS NULL; исторический NULL — активен);
 *   включена  → без ограничения is_active + include_deleted=true
 *               (активные, отключённые и ранее удалённые).
 */
export function visibilityParams(showDisabled) {
  return showDisabled
    ? { is_active: '', include_deleted: true }
    : { is_active: 'true', include_deleted: false };
}

export function useAdminUsers() {
  const [items, setItems]   = useState([]);
  const [total, setTotal]   = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);
  const [page, setPage]     = useState(1);
  const [size]              = useState(20);
  const [query, setQueryRaw]   = useState('');
  const [filters, setFiltersRaw] = useState({ role: '', showDisabled: false });
  const [tick, setTick]     = useState(0);

  const debouncedQuery = useDebounce(query, 300);

  function setQuery(val) {
    setQueryRaw(val);
    setPage(1);
  }

  function setFilters(val) {
    setFiltersRaw(val);
    setPage(1);
  }

  function refetch() {
    setTick((t) => t + 1);
  }

  useEffect(() => {
    let cancelled = false;
    let movedPage = false;
    setLoading(true);
    setError(null);

    getUsers({
      page,
      size,
      search: debouncedQuery,
      role:   filters.role,
      ...visibilityParams(filters.showDisabled),
    })
      .then((data) => {
        if (cancelled) return;
        const nextItems = data.items ?? [];
        const nextTotal = data.total ?? 0;
        // После отключения/восстановления страница могла опустеть —
        // переходим на существующую (загрузка продолжается там).
        const target = correctedPage(page, size, nextItems.length, nextTotal);
        if (target !== page) {
          movedPage = true;
          setPage(target);
          return;
        }
        setItems(nextItems);
        setTotal(nextTotal);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled && !movedPage) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [debouncedQuery, filters, page, size, tick]);

  return {
    items,
    loading,
    error,
    total,
    page,
    setPage,
    size,
    query,
    setQuery,
    filters,
    setFilters,
    refetch,
  };
}
