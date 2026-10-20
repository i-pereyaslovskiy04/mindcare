import Icon from '../../../../components/Icon/Icon';
import Button from '../../../../components/UI/Button/Button';
import Badge from '../../../../components/UI/Badge/Badge';
import styles from './CategoriesTable.module.css';

const SKELETON_ROWS = 6;

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU');
}

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 7 }, (_, i) => (
        <td key={i}><span className={styles.skeletonCell} /></td>
      ))}
    </tr>
  );
}

export default function CategoriesTable({
  items,
  loading,
  error,
  onEdit,
  onDelete,
  editLoadingId = null,
}) {
  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Название</th>
            <th>Slug</th>
            <th className={styles.colCenter}>Порядок</th>
            <th>Статус</th>
            <th className={styles.colCenter}>Материалы</th>
            <th>Дата</th>
            <th aria-label="Действия" />
          </tr>
        </thead>
        <tbody>
          {loading && Array.from({ length: SKELETON_ROWS }, (_, i) => (
            <SkeletonRow key={i} />
          ))}

          {!loading && error && (
            <tr>
              <td colSpan={7} className={styles.stateCell}>
                <span className={styles.errorText}>Ошибка загрузки: {error}</span>
              </td>
            </tr>
          )}

          {!loading && !error && items.length === 0 && (
            <tr>
              <td colSpan={7} className={styles.stateCell}>
                Типов материалов пока нет
              </td>
            </tr>
          )}

          {!loading && !error && items.map(item => (
            <tr key={item.id} className={styles.row}>
              <td>
                <span className={styles.name}>{item.name}</span>
              </td>
              <td>
                <code className={styles.slug}>{item.slug}</code>
              </td>
              <td className={styles.colCenter}>
                {item.display_order}
              </td>
              <td>
                <Badge tone={item.is_active ? 'success' : 'warning'}>
                  {item.is_active ? 'Активна' : 'Скрыта'}
                </Badge>
              </td>
              <td className={`${styles.colCenter} ${styles.count}`}>
                {item.article_count}
              </td>
              <td className={styles.date}>
                {formatDate(item.created_at)}
              </td>
              <td className={styles.actionsCell}>
                <div className={styles.actions}>
                  <Button
                    variant="icon"
                    size="sm"
                    onClick={() => onEdit(item)}
                    aria-label={`Редактировать «${item.name}»`}
                    title="Редактировать"
                    disabled={editLoadingId === item.id}
                  >
                    {editLoadingId === item.id
                      ? <span className={styles.spinner}>…</span>
                      : <Icon name="edit" size={15} />}
                  </Button>
                  <Button
                    variant="icon"
                    size="sm"
                    tone="danger"
                    onClick={() => onDelete(item)}
                    aria-label={`Деактивировать «${item.name}»`}
                    title="Деактивировать"
                  >
                    <Icon name="trash" size={15} />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
