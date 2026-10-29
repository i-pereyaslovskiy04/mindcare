import { RoleBadges, StatusBadge, UserRowActions, formatDate } from './UserCells';
import styles from './UsersCompactList.module.css';

const SKELETON_ITEMS = 3;

/**
 * Компактное представление /admin/users для узкой колонки: список записей
 * (не таблица, переложенная в карточки). ФИО и email переносятся целиком,
 * метаданные — список «подпись — значение», действия — под ними и всегда в
 * ширине экрана. Данные, состояния и действия — те же, что у UsersTable.
 */
export default function UsersCompactList({ items, loading, error, actionContext }) {
  if (loading) {
    return (
      <ul className={styles.list} aria-busy="true" aria-label="Пользователи">
        {Array.from({ length: SKELETON_ITEMS }, (_, i) => (
          <li key={i} className={styles.item}>
            <span className={styles.skeletonLine} />
            <span className={`${styles.skeletonLine} ${styles.skeletonShort}`} />
          </li>
        ))}
      </ul>
    );
  }

  if (error) {
    return <p className={`${styles.state} ${styles.error}`}>Ошибка загрузки: {error}</p>;
  }

  if (items.length === 0) {
    return <p className={styles.state}>Пользователи не найдены</p>;
  }

  return (
    <ul className={styles.list} aria-label="Пользователи">
      {items.map((item) => (
        <li key={item.uuid} className={`${styles.item}${item.deleted_at ? ` ${styles.itemDeleted}` : ''}`}>
          <div className={styles.head}>
            <h2 className={styles.name}>{item.full_name}</h2>
            <span className={styles.email}>{item.email}</span>
          </div>

          <dl className={styles.meta}>
            <div className={styles.metaRow}>
              <dt>Роли</dt>
              <dd><RoleBadges item={item} /></dd>
            </div>
            <div className={styles.metaRow}>
              <dt>Статус</dt>
              <dd><StatusBadge item={item} /></dd>
            </div>
            <div className={styles.metaRow}>
              <dt>Регистрация</dt>
              <dd>{formatDate(item.created_at)}</dd>
            </div>
            <div className={styles.metaRow}>
              <dt>Последний вход</dt>
              <dd>{formatDate(item.last_login)}</dd>
            </div>
          </dl>

          <UserRowActions item={item} actionContext={actionContext} />
        </li>
      ))}
    </ul>
  );
}
