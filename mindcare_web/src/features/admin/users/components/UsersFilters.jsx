import styles from './UsersFilters.module.css';

export default function UsersFilters({ query, onQueryChange, filters, onFiltersChange }) {
  return (
    <div className={styles.filters}>
      <input
        className={styles.search}
        type="text"
        placeholder="Поиск по имени или email..."
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
      />

      <select
        className={styles.select}
        value={filters.role}
        onChange={(e) => onFiltersChange({ ...filters, role: e.target.value })}
      >
        <option value="">Все роли</option>
        <option value="student">Студент</option>
        <option value="psychologist">Психолог</option>
        <option value="admin">Администратор</option>
        <option value="supervisor">Супервизор</option>
      </select>

      <select
        className={styles.select}
        value={filters.is_active}
        onChange={(e) => onFiltersChange({ ...filters, is_active: e.target.value })}
      >
        <option value="">Все</option>
        <option value="true">Активен</option>
        <option value="false">Заблокирован</option>
      </select>

      <label className={styles.checkboxLabel}>
        <input
          type="checkbox"
          checked={filters.includeDeleted}
          onChange={() => onFiltersChange({ ...filters, includeDeleted: !filters.includeDeleted })}
        />
        Показать удалённых
      </label>
    </div>
  );
}
