import Button from '../../../../components/UI/Button/Button';
import Badge from '../../../../components/UI/Badge/Badge';
import ResponsiveTable from '../../../../components/UI/ResponsiveTable/ResponsiveTable';
import ActionsMenu from '../../../../components/UI/ActionsMenu/ActionsMenu';
import TagList from '../../../../components/UI/TagList/TagList';
import {
  ARTICLE_STATUS_LABELS, ARTICLE_STATUS_TONES, articleStatus,
} from '../../../materials/lib/articleStatus';
import styles from './ArticlesTable.module.css';

// Видно до «+N»: строка таблицы не выше двух строк меток на набор.
const TYPES_VISIBLE = 2;
const TOPICS_VISIBLE = 2;

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU');
}

// Битая ссылка на обложку: вместо значка браузера — плашка media.
function hideBrokenImage(e) {
  e.currentTarget.style.visibility = 'hidden';
}

// Тип материала — категории (в админке «Типы материалов»), их может быть несколько.
function Types({ item }) {
  return (
    <TagList
      items={item.categories.map((c) => ({ key: c.id, label: c.name }))}
      maxVisible={TYPES_VISIBLE}
      label="Тип"
      variant="category"
    />
  );
}

function Topics({ item }) {
  return (
    <TagList
      items={item.tags.map((t) => ({ key: t.uuid, label: t.name }))}
      maxVisible={TOPICS_VISIBLE}
      label="Темы"
    />
  );
}

/**
 * Список материалов /admin/articles (только admin; модерация — отдельная
 * страница) на shared ResponsiveTable: здесь только содержимое, раскладку
 * wide / compact / mobile задаёт ResponsiveTable.
 *   wide    — Материал (обложка, заголовок, автор · дата) | Статус |
 *             Тип и темы | действия;
 *   compact/mobile — тип и темы уходят строками деталей и не сжимают заголовок.
 * Основное действие — «Редактировать», удаление — в меню «⋮».
 */
export default function ArticlesTable({ items, loading, error, onEdit, onDelete, editLoadingId = null }) {
  return (
    <ResponsiveTable
      label="Материалы"
      items={items}
      getKey={(item) => item.uuid}
      loading={loading}
      error={error ? `Ошибка загрузки: ${error}` : null}
      emptyText="Материалов пока нет"
      identity={{
        header: 'Материал',
        media: (item) => (item.cover_image_url
          ? <img src={item.cover_image_url} alt="" onError={hideBrokenImage} />
          : null),
        primary: (item) => item.title,
        secondary: (item) => (
          <>
            {item.created_by_name && (
              <>
                {item.created_by_name}
                <span aria-hidden="true"> · </span>
              </>
            )}
            <span className={styles.nowrap}>{formatDate(item.published_at || item.created_at)}</span>
          </>
        ),
      }}
      status={{
        header: 'Статус',
        render: (item) => (
          <Badge tone={ARTICLE_STATUS_TONES[articleStatus(item)]}>
            {ARTICLE_STATUS_LABELS[articleStatus(item)]}
          </Badge>
        ),
      }}
      columns={[
        {
          key: 'classification',
          header: 'Тип и темы',
          width: '14rem',
          render: (item) => (item.categories.length > 0 || item.tags.length > 0 ? (
            <div className={styles.classification}>
              <Types item={item} />
              <Topics item={item} />
            </div>
          ) : <span className={styles.none}>—</span>),
        },
      ]}
      meta={(item) => [
        ...(item.categories.length > 0 ? [{ label: 'Тип', value: <Types item={item} /> }] : []),
        ...(item.tags.length > 0 ? [{ label: 'Темы', value: <Topics item={item} /> }] : []),
      ]}
      actions={{
        primary: (item) => (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onEdit(item)}
            disabled={editLoadingId === item.uuid}
            aria-busy={editLoadingId === item.uuid || undefined}
            aria-label={`Редактировать «${item.title}»`}
          >
            Редактировать
          </Button>
        ),
        menu: (item) => (
          <ActionsMenu
            triggerLabel={`Другие действия: «${item.title}»`}
            items={[{ id: 'delete', label: 'Удалить', tone: 'danger', onSelect: () => onDelete(item) }]}
          />
        ),
      }}
    />
  );
}
