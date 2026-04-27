import { useState, useMemo } from 'react';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../components/AuthModal/AuthModal';
import PageHero from '../../components/Hero/PageHero';
import MaterialsToolbar from '../../components/Materials/MaterialsToolbar';
import MaterialsGrid from '../../components/Materials/MaterialsGrid';
import { MOCK_MATERIALS } from '../../components/Materials/mockMaterials';
import styles from './MaterialsPage.module.css';

const PAGE_SIZE = 6;

export default function MaterialsPage() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [sort, setSort] = useState('newest');
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const filtered = useMemo(() => {
    let items = MOCK_MATERIALS;

    if (category) {
      items = items.filter(i => i.tag === category);
    }

    if (search.trim()) {
      const q = search.trim().toLowerCase();
      items = items.filter(i =>
        i.title.toLowerCase().includes(q) ||
        i.description.toLowerCase().includes(q)
      );
    }

    return sort === 'oldest' ? [...items].reverse() : items;
  }, [search, category, sort]);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visibleCount < filtered.length;

  const handleSearch = v => { setSearch(v); setVisibleCount(PAGE_SIZE); };
  const handleCategory = v => { setCategory(v); setVisibleCount(PAGE_SIZE); };
  const handleSort = v => { setSort(v); setVisibleCount(PAGE_SIZE); };

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
          <MaterialsToolbar
            search={search}
            category={category}
            sort={sort}
            onSearch={handleSearch}
            onCategory={handleCategory}
            onSort={handleSort}
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
