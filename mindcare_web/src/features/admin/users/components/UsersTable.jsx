import TableShell from '../../../../components/UI/TableShell/TableShell';
import { RoleBadges, StatusBadge, UserRowActions, formatDate } from './UserCells';
import styles from './UsersTable.module.css';

const SKELETON_ROWS = 7;
const COLS = 4; // Пользователь, Роли и статус, Активность, Действия

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: COLS }, (_, i) => (
        <td key={i}><span className={styles.skeletonCell} /></td>
      ))}
    </tr>
  );
}

/**
 * Широкое представление /admin/users — семантическая таблица. ФИО и email —
 * одна колонка «Пользователь» (длинные значения переносятся, а не растягивают
 * таблицу), роли и статус — одна колонка бейджей, даты — одна колонка
 * «Активность». Действия — основное кнопкой,
 * остальные в меню (UserRowActions). На узкой колонке UsersDataView
 * показывает UsersCompactList с теми же данными и обработчиками.
 */
export default function UsersTable({ items, loading, error, actionContext }) {
  return (
    <TableShell caption="Пользователи" tableClassName={styles.table}>
      <thead>
        <tr>
          <th scope="col" className={styles.userCol}>Пользователь</th>
          <th scope="col" className={styles.badgesCol}>Роли и статус</th>
          <th scope="col">Активность</th>
          <th scope="col" className={styles.actionsCol}>
            <span className="visually-hidden">Действия</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {loading && Array.from({ length: SKELETON_ROWS }, (_, i) => <SkeletonRow key={i} />)}

        {!loading && error && (
          <tr>
            <td colSpan={COLS} className={styles.error}>
              Ошибка загрузки: {error}
            </td>
          </tr>
        )}

        {!loading && !error && items.length === 0 && (
          <tr>
            <td colSpan={COLS} className={styles.empty}>
              Пользователи не найдены
            </td>
          </tr>
        )}

        {!loading && !error && items.map((item) => (
          <tr key={item.uuid} className={`${styles.row}${item.deleted_at ? ` ${styles.rowDeleted}` : ''}`}>
            <td>
              <span className={styles.name}>{item.full_name}</span>
              <span className={styles.email}>{item.email}</span>
            </td>
            <td>
              <div className={styles.badges}>
                <RoleBadges item={item} />
                <StatusBadge item={item} />
              </div>
            </td>
            <td>
              <dl className={styles.dates}>
                <dt>Регистрация</dt>
                <dd>{formatDate(item.created_at)}</dd>
                <dt>Вход</dt>
                <dd>{formatDate(item.last_login)}</dd>
              </dl>
            </td>
            <td className={styles.actionsCell}>
              <UserRowActions item={item} actionContext={actionContext} className={styles.actions} />
            </td>
          </tr>
        ))}
      </tbody>
    </TableShell>
  );
}
