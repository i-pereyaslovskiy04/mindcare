import Icon from '../../../../components/Icon/Icon';
import Button from '../../../../components/UI/Button/Button';
import Tag from '../../../../components/UI/Tag/Tag';
import styles from './TagsTable.module.css';

const SKELETON_ROWS = 5;

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 6 }, (_, i) => (
        <td key={i}><span className={styles.skeletonCell} /></td>
      ))}
    </tr>
  );
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('ru-RU');
}

export default function TagsTable({ items, loading, error, onEdit, onDelete }) {
  const cols = 6;

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Название</th>
            <th className={styles.thCenter}>Статьи</th>
            <th className={styles.thCenter}>Новости</th>
            <th className={styles.thCenter}>Тесты</th>
            <th>Создан</th>
            <th aria-label="Действия" />
          </tr>
        </thead>
        <tbody>
          {loading && Array.from({ length: SKELETON_ROWS }, (_, i) => (
            <SkeletonRow key={i} />
          ))}

          {!loading && error && (
            <tr>
              <td colSpan={cols} className={styles.error}>
                Ошибка загрузки: {error}
              </td>
            </tr>
          )}

          {!loading && !error && items.length === 0 && (
            <tr>
              <td colSpan={cols} className={styles.empty}>
                Темы не найдены
              </td>
            </tr>
          )}

          {!loading && !error && items.map((item) => {
            const totalUsages = item.article_count + item.news_count + item.test_count;
            return (
              <tr key={item.uuid} className={styles.row}>
                <td>
                  <Tag variant="admin">{item.name}</Tag>
                </td>
                <td className={styles.count}>{item.article_count || '—'}</td>
                <td className={styles.count}>{item.news_count    || '—'}</td>
                <td className={styles.count}>{item.test_count    || '—'}</td>
                <td className={styles.date}>{formatDate(item.created_at)}</td>
                <td className={styles.actionsCell}>
                  <div className={styles.actions}>
                    <Button
                      variant="icon"
                      size="sm"
                      onClick={() => onEdit?.(item)}
                      aria-label={`Переименовать ${item.name}`}
                      title="Переименовать"
                    >
                      <Icon name="edit" size={15} />
                    </Button>
                    <Button
                      variant="icon"
                      size="sm"
                      tone="danger"
                      onClick={() => onDelete?.(item, totalUsages)}
                      aria-label={`Удалить ${item.name}`}
                      title="Удалить"
                    >
                      <Icon name="trash" size={15} />
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
