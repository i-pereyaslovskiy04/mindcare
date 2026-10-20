import { useState, useEffect, useCallback, useRef } from 'react';
import { getArticles, getPublicCategories } from '../api/articles.api';

const PAGE_SIZE = 6;

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

function normalizeArticle(item) {
  return {
    id:          item.uuid,
    uuid:        item.uuid,
    title:       item.title,
    description: item.excerpt || '',
    date:        formatDate(item.published_at || item.created_at),
    image:       item.cover_image_url || null,
    tag:         item.categories?.[0]?.name || '',
    topic:       item.tags?.[0]?.name || '',
    tags:        item.tags,
    categories:  item.categories,
  };
}

export function useMaterials() {
  const [rawItems, setRawItems]               = useState([]);
  const [total, setTotal]                     = useState(0);
  const [page, setPage]                       = useState(1);
  const [query, setQueryRaw]                  = useState('');
  const [selectedTags, setTagsRaw]            = useState([]);
  const [selectedTopics, setSelectedTopics]   = useState([]);
  const [sort, setSort]                       = useState('newest');
  const [categoryOptions, setCategoryOptions] = useState([]);
  const [loading, setLoading]                 = useState(true);
  const [error, setError]                     = useState(null);

  const reqId           = useRef(0);
  // ref вместо state — fetch-эффект не перезапускается при загрузке категорий
  const categoryMetaRef = useRef([]);

  useEffect(() => {
    getPublicCategories()
      .then(cats => {
        categoryMetaRef.current = cats;
        setCategoryOptions(cats.map(c => ({ value: c.name, label: c.name })));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const id = ++reqId.current;
    setLoading(true);
    setError(null);

    // API принимает один category_id — берём первый выбранный
    const cat        = categoryMetaRef.current.find(c => selectedTags.includes(c.name));
    const categoryId = cat?.id;

    getArticles({
      page,
      size:        PAGE_SIZE,
      search:      query.trim() || undefined,
      category_id: categoryId,
    })
      .then(data => {
        if (id !== reqId.current) return;
        const normalized = (data.items || []).map(normalizeArticle);
        setRawItems(prev => page === 1 ? normalized : [...prev, ...normalized]);
        setTotal(data.total ?? 0);
      })
      .catch(err => {
        if (id !== reqId.current) return;
        setError(err.message);
      })
      .finally(() => {
        if (id !== reqId.current) return;
        setLoading(false);
      });
  }, [page, query, selectedTags]); // categoryMeta исключён — используем ref

  const items   = sort === 'oldest' ? [...rawItems].reverse() : rawItems;
  const hasMore = rawItems.length < total;

  const loadMore = () => setPage(p => p + 1);

  const setQuery = useCallback((q) => {
    setQueryRaw(q);
    setPage(1);
    setRawItems([]);
  }, []);

  // Single-select: API принимает один category_id.
  // FiltersDropdown передаёт новый массив при каждом клике:
  //   выбор нового тега → [...prev, newTag] → берём только newTag
  //   снятие тега      → prev.filter(...)   → justAdded=undefined → []
  const setSelectedTags = useCallback((tags) => {
    setTagsRaw(prev => {
      const justAdded = tags.find(t => !prev.includes(t));
      return justAdded ? [justAdded] : [];
    });
    setPage(1);
    setRawItems([]);
  }, []);

  return {
    query,          setQuery,
    selectedTags,   setSelectedTags,
    selectedTopics, setSelectedTopics,
    sort,           setSort,
    tagOptions:     categoryOptions,
    topicOptions:   [],
    items,
    hasMore,
    loadMore,
    loading,
    error,
  };
}
