import Icon from '../../../../pages/student/components/Icon';
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
                <span className={`${styles.badge} ${item.is_active ? styles.active : styles.inactive}`}>
                  {item.is_active ? 'Активна' : 'Скрыта'}
                </span>
              </td>
              <td className={`${styles.colCenter} ${styles.count}`}>
                {item.article_count}
              </td>
              <td className={styles.date}>
                {formatDate(item.created_at)}
              </td>
              <td className={styles.actions}>
                <button
                  type="button"
                  className={styles.iconBtn}
                  onClick={() => onEdit(item)}
                  aria-label={`Редактировать «${item.name}»`}
                  disabled={editLoadingId === item.id}
                >
                  {editLoadingId === item.id
                    ? <span className={styles.spinner}>…</span>
                    : <Icon name="edit" size={15} />}
                </button>
                <button
                  type="button"
                  className={`${styles.iconBtn} ${styles.iconBtnDanger}`}
                  onClick={() => onDelete(item)}
                  aria-label={`Деактивировать «${item.name}»`}
                >
                  <Icon name="trash" size={15} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
