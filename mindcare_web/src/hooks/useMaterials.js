import { useState, useMemo, useEffect } from 'react';
import { MOCK_MATERIALS, CATEGORIES } from '../data/materials.mock';

const PAGE_SIZE = 6;

export const TAG_OPTIONS = CATEGORIES.map((c) => ({ value: c, label: c }));

export function useMaterials() {
  const [query, setQuery] = useState('');
  const [selectedTags, setSelectedTags] = useState([]);
  const [sort, setSort] = useState('newest');
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [query, selectedTags, sort]);

  const filtered = useMemo(() => {
    let items = MOCK_MATERIALS;

    if (selectedTags.length > 0) {
      items = items.filter((i) => selectedTags.includes(i.tag));
    }

    if (query.trim()) {
      const q = query.trim().toLowerCase();
      items = items.filter(
        (i) =>
          i.title.toLowerCase().includes(q) ||
          i.description.toLowerCase().includes(q) ||
          i.tag.toLowerCase().includes(q)
      );
    }

    return sort === 'oldest' ? [...items].reverse() : items;
  }, [query, selectedTags, sort]);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visibleCount < filtered.length;
  const loadMore = () => setVisibleCount((c) => c + PAGE_SIZE);

  return {
    query, setQuery,
    selectedTags, setSelectedTags,
    sort, setSort,
    visible,
    hasMore,
    loadMore,
  };
}
