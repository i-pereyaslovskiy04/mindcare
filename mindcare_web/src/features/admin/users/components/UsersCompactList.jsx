import {
  RoleBadges, StatusBadge, UserMoreActions, UserPrimaryAction, formatDate,
} from './UserCells';
import styles from './UsersCompactList.module.css';

const SKELETON_ITEMS = 4;

/**
 * Список пользователей для колонки, где таблица не помещается: строки данных
 * в одной карточке с разделителями, не карточки профиля. Одна разметка —
 * две раскладки по ширине колонки (container query в CSS):
 *   compact — строка: пользователь | роли и статус | действие ⋮,
 *             под ней даты вторичной строкой;
 *   mobile  — пользователь и ⋮, ниже роли и статус, даты, основное действие.
 * Части записи: primary (ФИО), secondary (email), meta (роли, статус),
 * actions (основное + меню), details (даты). Данные, состояния и действия —
 * те же, что у UsersTable.
 */
export default function UsersCompactList({ items, loading, error, actionContext }) {
  if (loading) {
    return (
      <ul className={styles.list} aria-busy="true" aria-label="Пользователи">
        {Array.from({ length: SKELETON_ITEMS }, (_, i) => (
          <li key={i} className={styles.skeletonItem}>
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
          <div className={styles.who}>
            <h2 className={styles.name}>{item.full_name}</h2>
            <span className={styles.email}>{item.email}</span>
          </div>

          <div className={styles.badges}>
            <RoleBadges item={item} />
            <StatusBadge item={item} />
          </div>

          <dl className={styles.dates}>
            <div className={styles.date}>
              <dt>Регистрация</dt>
              <dd>{formatDate(item.created_at)}</dd>
            </div>
            <div className={styles.date}>
              <dt>Последний вход</dt>
              <dd>{formatDate(item.last_login)}</dd>
            </div>
          </dl>

          <UserPrimaryAction item={item} actionContext={actionContext} className={styles.primary} />
          <UserMoreActions item={item} actionContext={actionContext} className={styles.more} />
        </li>
      ))}
    </ul>
  );
}
