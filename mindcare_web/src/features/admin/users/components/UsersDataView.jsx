import UsersTable from './UsersTable';
import UsersCompactList from './UsersCompactList';
import styles from './UsersDataView.module.css';

/**
 * Данные текущей страницы /admin/users в двух представлениях: таблица
 * (широкая колонка) и компактный список (узкая). Оба получают одни и те же
 * items/состояния и один actionContext (обработчики страницы), поэтому смена
 * ширины не делает запросов и ничего не сбрасывает. Какое представление видно,
 * решает CSS по ширине самой колонки (container query); без поддержки
 * container queries остаётся компактный список — он работает на любой ширине.
 */
export default function UsersDataView({ items, loading, error, actionContext }) {
  const props = { items, loading, error, actionContext };
  return (
    <div className={styles.view}>
      <div className={styles.wide}>
        <UsersTable {...props} />
      </div>
      <div className={styles.compact}>
        <UsersCompactList {...props} />
      </div>
    </div>
  );
}
