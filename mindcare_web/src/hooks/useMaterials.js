import { useState, useMemo, useEffect } from 'react';
import { MOCK_MATERIALS, CATEGORIES, TOPICS } from '../data/materials.mock';

const PAGE_SIZE = 6;

export const TAG_OPTIONS   = CATEGORIES.map((c) => ({ value: c, label: c }));
export const TOPIC_OPTIONS = TOPICS.map((t)     => ({ value: t, label: t }));

export function useMaterials() {
  const [query,          setQuery]          = useState('');
  const [selectedTags,   setSelectedTags]   = useState([]);
  const [selectedTopics, setSelectedTopics] = useState([]);
  const [sort,           setSort]           = useState('newest');
  const [visibleCount,   setVisibleCount]   = useState(PAGE_SIZE);

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [query, selectedTags, selectedTopics, sort]);

  const filtered = useMemo(() => {
    let items = MOCK_MATERIALS;

    if (selectedTags.length > 0) {
      items = items.filter((i) => selectedTags.includes(i.tag));
    }

    if (selectedTopics.length > 0) {
      items = items.filter((i) => selectedTopics.includes(i.topic));
    }

    if (query.trim()) {
      const q = query.trim().toLowerCase();
      items = items.filter(
        (i) =>
          i.title.toLowerCase().includes(q) ||
          i.description.toLowerCase().includes(q) ||
          i.tag.toLowerCase().includes(q) ||
          i.topic.toLowerCase().includes(q),
      );
    }

    return sort === 'oldest' ? [...items].reverse() : items;
  }, [query, selectedTags, selectedTopics, sort]);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visibleCount < filtered.length;
  const loadMore = () => setVisibleCount((c) => c + PAGE_SIZE);

  return {
    query, setQuery,
    selectedTags,   setSelectedTags,
    selectedTopics, setSelectedTopics,
    sort, setSort,
    visible,
    hasMore,
    loadMore,
  };
}
