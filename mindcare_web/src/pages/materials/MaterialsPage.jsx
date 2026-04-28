import { useState, useMemo, useEffect } from 'react';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../components/AuthModal/AuthModal';
import PageHero from '../../components/Hero/PageHero';
import SearchBar from './components/SearchBar';
import MaterialsGrid from './components/MaterialsGrid';
import { MOCK_MATERIALS, CATEGORIES } from './components/mockMaterials';
import styles from './MaterialsPage.module.css';

const PAGE_SIZE = 6;

const TAG_OPTIONS = CATEGORIES.map(c => ({ value: c, label: c }));

export default function MaterialsPage() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  // SearchBar calls onQueryChange with already-debounced value (300ms inside)
  const [query, setQuery] = useState('');
  const [selectedTags, setSelectedTags] = useState([]);
  const [sort, setSort] = useState('newest');
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  // Reset pagination on any filter change
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [query, selectedTags, sort]);

  const filtered = useMemo(() => {
    let items = MOCK_MATERIALS;

    if (selectedTags.length > 0) {
      items = items.filter(i => selectedTags.includes(i.tag));
    }

    if (query.trim()) {
      const q = query.trim().toLowerCase();
      items = items.filter(i =>
        i.title.toLowerCase().includes(q) ||
        i.description.toLowerCase().includes(q) ||
        i.tag.toLowerCase().includes(q)
      );
    }

    return sort === 'oldest' ? [...items].reverse() : items;
  }, [query, selectedTags, sort]);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visibleCount < filtered.length;

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />
      <PageHero
        eyebrow="Ресурсный центр практической психологии"
        title="Материалы"
        sub="Статьи, вебинары и упражнения для поддержки психологического здоровья"
      />

      <section className="section-wrap alt">
        <div className="container">
          <SearchBar
            onQueryChange={setQuery}
            selectedTags={selectedTags}
            onTagsChange={setSelectedTags}
            sort={sort}
            onSortChange={setSort}
            tagOptions={TAG_OPTIONS}
          />
          <MaterialsGrid items={visible} />

          {hasMore && (
            <div className={styles.loadMore}>
              <button
                className={styles.loadMoreBtn}
                onClick={() => setVisibleCount(c => c + PAGE_SIZE)}
              >
                Загрузить ещё
              </button>
            </div>
          )}
        </div>
      </section>

      <Footer />
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </>
  );
}
