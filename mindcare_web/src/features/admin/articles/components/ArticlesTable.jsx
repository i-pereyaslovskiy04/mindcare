import Icon from '../../../../components/Icon/Icon';
import styles from './ArticlesTable.module.css';

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

export default function ArticlesTable({ items, loading, error, onEdit, onDelete, editLoadingId = null }) {
  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.colCover} />
            <th>Заголовок</th>
            <th>Тип</th>
            <th>Теги</th>
            <th>Статус</th>
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
              <td colSpan={7} className={styles.stateCell}>Материалов пока нет</td>
            </tr>
          )}

          {!loading && !error && items.map(item => (
            <tr key={item.uuid} className={styles.row}>
              <td className={styles.colCover}>
                {item.cover_image_url
                  ? <img src={item.cover_image_url} alt="" className={styles.thumb} />
                  : <div className={styles.thumbPlaceholder} />}
              </td>
              <td>
                <span className={styles.title}>{item.title}</span>
                {item.excerpt && (
                  <span className={styles.excerpt}>{item.excerpt}</span>
                )}
                {item.created_by_name && (
                  <span className={styles.meta}>{item.created_by_name}</span>
                )}
              </td>
              <td>
                <div className={styles.tags}>
                  {item.categories.map(c => (
                    <span key={c.id} className={styles.category}>{c.name}</span>
                  ))}
                </div>
              </td>
              <td>
                <div className={styles.tags}>
                  {item.tags.map(t => (
                    <span key={t.uuid} className={styles.tag}>{t.name}</span>
                  ))}
                </div>
              </td>
              <td>
                <span className={`${styles.badge} ${item.is_published ? styles.published : styles.draft}`}>
                  {item.is_published ? 'Опубликовано' : 'Черновик'}
                </span>
              </td>
              <td className={styles.date}>
                {formatDate(item.published_at || item.created_at)}
              </td>
              <td className={styles.actions}>
                <button
                  type="button"
                  className={styles.iconBtn}
                  onClick={() => onEdit(item)}
                  aria-label={`Редактировать «${item.title}»`}
                  disabled={editLoadingId === item.uuid}
                >
                  {editLoadingId === item.uuid
                    ? <span className={styles.spinner}>…</span>
                    : <Icon name="edit" size={15} />}
                </button>
                <button
                  type="button"
                  className={`${styles.iconBtn} ${styles.iconBtnDanger}`}
                  onClick={() => onDelete(item)}
                  aria-label={`Удалить «${item.title}»`}
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
