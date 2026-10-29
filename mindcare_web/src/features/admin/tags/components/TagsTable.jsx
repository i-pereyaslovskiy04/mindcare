import Button from '../../../../components/UI/Button/Button';
import ResponsiveTable from '../../../../components/UI/ResponsiveTable/ResponsiveTable';
import ActionsMenu from '../../../../components/UI/ActionsMenu/ActionsMenu';
import styles from './TagsTable.module.css';

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('ru-RU');
}

const USAGES = [
  ['article_count', 'Статьи'],
  ['news_count', 'Новости'],
  ['test_count', 'Тесты'],
];

// Только ненулевые счётчики: [{ label, value }].
const usages = (item) => USAGES
  .filter(([field]) => item[field] > 0)
  .map(([field, label]) => ({ label, value: item[field] }));

/**
 * Справочник тем (/admin/tags, UI-подпись «Темы») на shared ResponsiveTable.
 * Название темы — идентификатор записи: выводится полностью и переносится,
 * без обрезки. Использование — ненулевые счётчики статей, новостей и
 * тестов; без связей — «Не используется».
 * Основное действие — «Переименовать», удаление — в меню «⋮» (страница
 * предупреждает о связях по общему числу использований).
 */
export default function TagsTable({ items, loading, error, onEdit, onDelete }) {
  return (
    <ResponsiveTable
      label="Темы"
      items={items}
      getKey={(item) => item.uuid}
      loading={loading}
      error={error ? `Ошибка загрузки: ${error}` : null}
      emptyText="Темы не найдены"
      identity={{
        header: 'Тема',
        primary: (item) => item.name,
        secondary: (item) => `создана ${formatDate(item.created_at)}`,
      }}
      columns={[
        {
          key: 'usage',
          header: 'Использование',
          render: (item) => {
            const used = usages(item);
            if (used.length === 0) return <span className={styles.unused}>Не используется</span>;
            return (
              <span className={styles.usage}>
                {used.map(({ label, value }, i) => (
                  <span key={label}>
                    {i > 0 && <span aria-hidden="true"> · </span>}
                    <span className={styles.nowrap}>{label} {value}</span>
                  </span>
                ))}
              </span>
            );
          },
        },
      ]}
      meta={(item) => {
        const used = usages(item);
        return used.length > 0 ? used : [{ label: 'Использование', value: 'нет' }];
      }}
      actions={{
        primary: (item) => (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onEdit?.(item)}
            aria-label={`Переименовать ${item.name}`}
          >
            Переименовать
          </Button>
        ),
        menu: (item) => (
          <ActionsMenu
            triggerLabel={`Другие действия: ${item.name}`}
            items={[{
              id: 'delete', label: 'Удалить', tone: 'danger',
              onSelect: () => onDelete?.(item, item.article_count + item.news_count + item.test_count),
            }]}
          />
        ),
      }}
    />
  );
}
