import styles from './ArticlesTable.module.css';

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export default function ArticlesTable({ items, onEdit, onDelete }) {
  if (!items.length) {
    return <p className={styles.empty}>Материалов пока нет.</p>;
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.colCover} />
            <th className={styles.colTitle}>Заголовок</th>
            <th className={styles.colCats}>Тип</th>
            <th className={styles.colTags}>Теги</th>
            <th className={styles.colStatus}>Статус</th>
            <th className={styles.colDate}>Дата</th>
            <th className={styles.colActions} />
          </tr>
        </thead>
        <tbody>
          {items.map(item => (
            <tr key={item.uuid} className={styles.row}>
              <td className={styles.colCover}>
                {item.cover_image_url ? (
                  <img src={item.cover_image_url} alt="" className={styles.thumb} />
                ) : (
                  <div className={styles.thumbPlaceholder} />
                )}
              </td>
              <td className={styles.colTitle}>
                <span className={styles.title}>{item.title}</span>
                {item.excerpt && (
                  <span className={styles.excerpt}>{item.excerpt}</span>
                )}
                {item.created_by_name && (
                  <span className={styles.author}>{item.created_by_name}</span>
                )}
              </td>
              <td className={styles.colCats}>
                <div className={styles.tags}>
                  {item.categories.map(c => (
                    <span key={c.id} className={styles.catBadge}>{c.name}</span>
                  ))}
                </div>
              </td>
              <td className={styles.colTags}>
                <div className={styles.tags}>
                  {item.tags.map(t => (
                    <span key={t.uuid} className={styles.tag}>{t.name}</span>
                  ))}
                </div>
              </td>
              <td className={styles.colStatus}>
                <span className={`${styles.badge} ${item.is_published ? styles.published : styles.draft}`}>
                  {item.is_published ? 'Опубликовано' : 'Черновик'}
                </span>
              </td>
              <td className={styles.colDate}>{formatDate(item.published_at || item.created_at)}</td>
              <td className={styles.colActions}>
                <button className={styles.btnEdit} onClick={() => onEdit(item)} title="Редактировать">✎</button>
                <button className={styles.btnDelete} onClick={() => onDelete(item)} title="Удалить">🗑</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
