import { useState } from 'react';
import Navbar from '../../components/Navbar/Navbar';
import Button from '../../components/UI/Button/Button';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
import PageHero from '../../components/Hero/PageHero';
import SearchBar from './components/SearchBar';
import MaterialsGrid from './components/MaterialsGrid';
import { useMaterials } from '../../hooks/useMaterials';
import styles from './MaterialsPage.module.css';

export default function MaterialsPage() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  const {
    setQuery,
    selectedTags,   setSelectedTags,
    selectedTopics, setSelectedTopics,
    sort,           setSort,
    tagOptions,
    topicOptions,
    items,
    hasMore,
    loadMore,
    loading,
    error,
  } = useMaterials();

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
            selectedTopics={selectedTopics}
            onTopicsChange={setSelectedTopics}
            sort={sort}
            onSortChange={setSort}
            tagOptions={tagOptions}
            topicOptions={topicOptions}
          />

          {error && <p className={styles.error}>Ошибка загрузки: {error}</p>}

          <MaterialsGrid items={items} loading={loading} />

          {hasMore && !loading && (
            <div className={styles.loadMore}>
              <Button type="button" variant="secondary" onClick={loadMore}>
                Загрузить ещё
              </Button>
            </div>
          )}
        </div>
      </section>

      <Footer />
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </>
  );
}
