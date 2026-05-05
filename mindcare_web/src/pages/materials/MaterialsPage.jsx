import { useState } from 'react';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
import PageHero from '../../components/Hero/PageHero';
import SearchBar from './components/SearchBar';
import MaterialsGrid from './components/MaterialsGrid';
import { useMaterials, TAG_OPTIONS, TOPIC_OPTIONS } from '../../hooks/useMaterials';
import styles from './MaterialsPage.module.css';

export default function MaterialsPage() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  const {
    setQuery,
    selectedTags,   setSelectedTags,
    selectedTopics, setSelectedTopics,
    sort, setSort,
    visible,
    hasMore,
    loadMore,
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
            tagOptions={TAG_OPTIONS}
            topicOptions={TOPIC_OPTIONS}
          />
          <MaterialsGrid items={visible} />

          {hasMore && (
            <div className={styles.loadMore}>
              <button className={styles.loadMoreBtn} onClick={loadMore}>
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
