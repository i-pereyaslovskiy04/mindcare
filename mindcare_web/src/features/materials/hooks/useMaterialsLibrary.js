import { useCallback, useEffect, useRef, useState } from 'react';
import { getArticles, getPublicCategories } from '../../../api/articles.api';
import { getFavoriteMaterials } from '../../../api/materialFavorites.api';
import { normalizeArticle } from '../lib/normalizeArticle';

export const MATERIALS_PAGE_SIZE = 6;

/**
 * Библиотека опубликованных материалов (публичный API /api/articles).
 *
 * Только то, что поддерживает серверный контракт: поиск по названию, один
 * category_id и постраничная выдача (новые сначала — порядок задаёт сервер).
 * Сортировки и фильтра по темам здесь нет: API их не принимает, а имитация на
 * загруженной части списка вводила бы в заблуждение.
 *
 * favoritesOnly — та же выдача, но только из серверного избранного
 * пользователя (/api/materials/favorites, ADR-034); переключение сбрасывает
 * страницу. reload() — перечитать с первой страницы (после изменения
 * избранного в режиме «только избранное»).
 */
export function useMaterialsLibrary({ pageSize = MATERIALS_PAGE_SIZE } = {}) {
  const [items, setItems]       = useState([]);
  const [total, setTotal]       = useState(0);
  const [page, setPage]         = useState(1);
  const [query, setQueryRaw]    = useState('');   // уже после trim
  const [category, setCategoryRaw] = useState(null);   // id категории или null
  const [categoryOptions, setCategoryOptions] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [favoritesOnly, setFavoritesOnlyRaw] = useState(false);

  const reqId = useRef(0);

  useEffect(() => {
    let alive = true;
    getPublicCategories()
      .then(cats => {
        if (!alive) return;
        setCategoryOptions(
          (Array.isArray(cats) ? cats : []).map(c => ({ value: c.id, label: c.name })),
        );
      })
      // Без категорий фильтр просто не показывается; список материалов от этого
      // не зависит, поэтому отдельной ошибки нет.
      .catch(() => { if (alive) setCategoryOptions([]); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    const id = ++reqId.current;
    setLoading(true);
    setError(null);
    const fetchPage = favoritesOnly ? getFavoriteMaterials : getArticles;
    fetchPage({
      page,
      size:        pageSize,
      search:      query || undefined,
      category_id: category ?? undefined,
    })
      .then(data => {
        if (id !== reqId.current) return;
        const normalized = (data?.items || []).map(normalizeArticle);
        setItems(prev => (page === 1 ? normalized : [...prev, ...normalized]));
        setTotal(data?.total ?? 0);
      })
      .catch(err => {
        if (id !== reqId.current) return;
        setError(err?.message || 'Не удалось загрузить материалы');
      })
      .finally(() => {
        if (id === reqId.current) setLoading(false);
      });
  }, [page, query, category, pageSize, reloadKey, favoritesOnly]);

  // Текущие параметры выборки — для сравнения без лишних замыканий.
  const queryRef = useRef('');
  const categoryRef = useRef(null);

  // Тот же запрос (после trim) или та же категория — no-op: список не
  // очищается. Иначе очистка без загрузки: эффект не перезапустился бы, потому
  // что параметры выборки не изменились (повтор после debounce, «сон » → «сон»).
  const setQuery = useCallback((q) => {
    const next = (q ?? '').trim();
    if (next === queryRef.current) return;
    queryRef.current = next;
    setQueryRaw(next);
    setPage(1);
    setItems([]);
  }, []);

  const setCategory = useCallback((value) => {
    const next = value ?? null;
    if (next === categoryRef.current) return;
    categoryRef.current = next;
    setCategoryRaw(next);
    setPage(1);
    setItems([]);
  }, []);

  const favoritesRef = useRef(false);
  const setFavoritesOnly = useCallback((value) => {
    const next = Boolean(value);
    if (next === favoritesRef.current) return;
    favoritesRef.current = next;
    setFavoritesOnlyRaw(next);
    setPage(1);
    setItems([]);
  }, []);

  const reload = useCallback(() => {
    setPage(1);
    setItems([]);
    setReloadKey(k => k + 1);
  }, []);

  const loadMore = useCallback(() => setPage(p => p + 1), []);

  // Повтор после ошибки: страница, на которой случился сбой, запрашивается снова
  // (уже загруженные страницы не теряются).
  const refetch = useCallback(() => setReloadKey(k => k + 1), []);

  return {
    items,
    total,
    loading,
    error,
    query,
    setQuery,
    category,
    setCategory,
    categoryOptions,
    hasMore: items.length < total,
    loadMore,
    refetch,
    favoritesOnly,
    setFavoritesOnly,
    reload,
  };
}
