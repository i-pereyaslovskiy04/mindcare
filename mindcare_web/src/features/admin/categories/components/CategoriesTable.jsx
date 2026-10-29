import Button from '../../../../components/UI/Button/Button';
import Badge from '../../../../components/UI/Badge/Badge';
import ResponsiveTable from '../../../../components/UI/ResponsiveTable/ResponsiveTable';
import ActionsMenu from '../../../../components/UI/ActionsMenu/ActionsMenu';
import styles from './CategoriesTable.module.css';

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU');
}

/**
 * Справочник категорий (/admin/categories, UI-подпись «Типы материалов») на
 * shared ResponsiveTable: название и slug | статус | параметры (порядок,
 * число материалов, дата) | действия. Основное действие — «Редактировать»,
 * «Деактивировать» (мягкое скрытие, страница подтверждает) — в меню «⋮».
 */
export default function CategoriesTable({
  items,
  loading,
  error,
  onEdit,
  onDelete,
  editLoadingId = null,
}) {
  return (
    <ResponsiveTable
      label="Типы материалов"
      items={items}
      getKey={(item) => item.id}
      loading={loading}
      error={error ? `Ошибка загрузки: ${error}` : null}
      emptyText="Типов материалов пока нет"
      identity={{
        header: 'Тип материала',
        primary: (item) => item.name,
        secondary: (item) => <code className={styles.slug}>{item.slug}</code>,
      }}
      status={{
        header: 'Статус',
        render: (item) => (
          <Badge tone={item.is_active ? 'success' : 'warning'}>
            {item.is_active ? 'Активна' : 'Скрыта'}
          </Badge>
        ),
      }}
      columns={[
        {
          key: 'params',
          header: 'Параметры',
          render: (item) => (
            <span className={styles.params}>
              <span className={styles.nowrap}>Порядок {item.display_order}</span>
              <span aria-hidden="true"> · </span>
              <span className={styles.nowrap}>Материалов {item.article_count}</span>
              <span aria-hidden="true"> · </span>
              <span className={styles.nowrap}>{formatDate(item.created_at)}</span>
            </span>
          ),
        },
      ]}
      meta={(item) => [
        { label: 'Порядок', value: item.display_order },
        { label: 'Материалов', value: item.article_count },
        { label: 'Создана', value: formatDate(item.created_at) },
      ]}
      actions={{
        primary: (item) => (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onEdit(item)}
            disabled={editLoadingId === item.id}
            aria-busy={editLoadingId === item.id || undefined}
            aria-label={`Редактировать «${item.name}»`}
          >
            Редактировать
          </Button>
        ),
        menu: (item) => (
          <ActionsMenu
            triggerLabel={`Другие действия: «${item.name}»`}
            items={[{ id: 'deactivate', label: 'Деактивировать', tone: 'danger', onSelect: () => onDelete(item) }]}
          />
        ),
      }}
    />
  );
}
