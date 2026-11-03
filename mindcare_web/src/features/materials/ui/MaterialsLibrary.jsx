import Icon from '../../../components/Icon/Icon';
import Button from '../../../components/UI/Button/Button';
import FilterChip from '../../../components/UI/FilterChip/FilterChip';
import SearchBar from '../components/SearchBar';
import MaterialsGrid from '../components/MaterialsGrid';
import useMaterialFavorites from '../hooks/useMaterialFavorites';
import { useMaterialsLibrary } from '../hooks/useMaterialsLibrary';
import styles from './MaterialsLibrary.module.css';

const COMPACT_PAGE_SIZE = 8;

/**
 * Список опубликованных материалов без обвязки страницы (Navbar/Footer или
 * CabinetLayout добавляет вызывающая страница).
 *
 * getItemPath(id) — адрес чтения материала в текущем контексте:
 * /materials/:id на сайте, /student/materials/:id и т. п. в кабинетах.
 * variant: 'card' — карточки публичного сайта; 'compact' — компактные
 * карточки кабинетов (4 колонки, 8 на страницу).
 * withFavorites — серверное избранное (ADR-034, только compact в кабинетах):
 * сердечко на карточке и фильтр «Избранное». На публичном сайте и в режиме
 * «под именем» выключено.
 */
export default function MaterialsLibrary({ getItemPath, variant = 'card', withFavorites = false }) {
  const compact = variant === 'compact';
  const {
    items, total, loading, error,
    query, setQuery,
    category, setCategory, categoryOptions,
    tag, setTag, tagOptions,
    hasMore, loadMore, refetch,
    favoritesOnly, setFavoritesOnly, reload,
  } = useMaterialsLibrary(compact ? { pageSize: COMPACT_PAGE_SIZE } : undefined);

  const favoritesEnabled = withFavorites && compact;
  const favorites = useMaterialFavorites({
    enabled: favoritesEnabled,
    // В режиме «только избранное» снятая отметка убирает карточку из выдачи.
    onChanged: () => { if (favoritesOnly) reload(); },
  });

  const filtered  = Boolean(query.trim()) || category != null || tag != null;
  const emptyText = favoritesOnly
    ? (filtered
      ? 'В избранном ничего не найдено по этому запросу.'
      : 'В избранном пока ничего нет. Отметьте материал сердечком, чтобы вернуться к нему позже.')
    : filtered
      ? 'По вашему запросу ничего не найдено. Попробуйте изменить поиск, тип материала или тему.'
      : 'Опубликованных материалов пока нет.';
  const showGrid  = !(error && items.length === 0);

  return (
    <div className={styles.library}>
      <SearchBar
        onQueryChange={setQuery}
        category={category}
        onCategoryChange={setCategory}
        categoryOptions={categoryOptions}
        tag={tag}
        onTagChange={setTag}
        tagOptions={tagOptions}
      />

      {favoritesEnabled && (
        <div className={styles.favsRow}>
          <FilterChip
            active={favoritesOnly}
            onClick={() => setFavoritesOnly(!favoritesOnly)}
            icon={<Icon name={favoritesOnly ? 'heart' : 'heart-o'} size={12} />}
          >
            Избранное · {favorites.count}
          </FilterChip>
        </div>
      )}
      {favoritesEnabled && favorites.actionError && (
        <p className={styles.favError} role="alert">{favorites.actionError}</p>
      )}

      {!loading && !error && (
        <p className="visually-hidden" aria-live="polite">
          {items.length > 0 ? `Найдено материалов: ${total}` : emptyText}
        </p>
      )}

      {error && (
        <div className={styles.errorBox} role="alert">
          <p className={styles.errorText}>Не удалось загрузить материалы. Проверьте соединение и повторите попытку.</p>
          <Button type="button" variant="secondary" size="sm" onClick={refetch}>
            Повторить
          </Button>
        </div>
      )}

      {showGrid && (
        <MaterialsGrid
          items={items}
          loading={loading}
          getItemPath={getItemPath}
          emptyText={emptyText}
          variant={variant}
          favorites={favoritesEnabled && favorites.loaded ? favorites : null}
        />
      )}

      {hasMore && !loading && !error && (
        <div className={styles.loadMore}>
          <Button type="button" variant="secondary" onClick={loadMore}>
            Загрузить ещё
          </Button>
        </div>
      )}
    </div>
  );
}
