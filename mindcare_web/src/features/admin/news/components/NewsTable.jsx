import Button from '../../../../components/UI/Button/Button';
import Badge from '../../../../components/UI/Badge/Badge';
import ResponsiveTable from '../../../../components/UI/ResponsiveTable/ResponsiveTable';
import ActionsMenu from '../../../../components/UI/ActionsMenu/ActionsMenu';
import TagList from '../../../../components/UI/TagList/TagList';
import styles from './NewsTable.module.css';

// Тем видно до «+N»: две — строка таблицы не выше двух строк меток.
const TOPICS_VISIBLE = 2;

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU');
}

// Битая ссылка на обложку: вместо значка браузера — плашка media.
function hideBrokenImage(e) {
  e.currentTarget.style.visibility = 'hidden';
}

function topicItems(item) {
  return item.tags.map((t) => ({ key: t.uuid, label: t.name }));
}

function Topics({ item }) {
  return <TagList items={topicItems(item)} maxVisible={TOPICS_VISIBLE} label="Темы" />;
}

/**
 * Список новостей admin и supervisor (один компонент — права обеих ролей на
 * /api/admin/news одинаковы) на shared ResponsiveTable: здесь только
 * содержимое, раскладку wide / compact / mobile задаёт ResponsiveTable.
 *   wide    — Новость (обложка, заголовок, автор · дата) | Статус | Темы | действия;
 *   compact/mobile — темы уходят строкой деталей и не сжимают заголовок.
 * Основное действие — «Редактировать», удаление — в меню «⋮».
 */
export default function NewsTable({ items, loading, error, onEdit, onDelete, editLoadingId = null }) {
  return (
    <ResponsiveTable
      label="Новости"
      items={items}
      getKey={(item) => item.uuid}
      loading={loading}
      error={error ? `Ошибка загрузки: ${error}` : null}
      emptyText="Новостей пока нет"
      identity={{
        header: 'Новость',
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
          <Badge tone={item.is_published ? 'success' : 'warning'}>
            {item.is_published ? 'Опубликовано' : 'Черновик'}
          </Badge>
        ),
      }}
      columns={[
        {
          key: 'topics',
          header: 'Темы',
          width: '14rem',
          render: (item) => (item.tags.length > 0
            ? <Topics item={item} />
            : <span className={styles.none}>—</span>),
        },
      ]}
      meta={(item) => (item.tags.length > 0 ? [{ label: 'Темы', value: <Topics item={item} /> }] : [])}
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
