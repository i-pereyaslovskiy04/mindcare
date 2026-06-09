import Select from '../../../../components/UI/Select/Select';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import styles from './UsersFilters.module.css';

const ROLE_OPTIONS = [
  { value: '',             label: 'Все роли' },
  { value: 'student',      label: 'Студент' },
  { value: 'psychologist', label: 'Психолог' },
  { value: 'admin',        label: 'Администратор' },
  { value: 'supervisor',   label: 'Супервизор' },
];

const STATUS_OPTIONS = [
  { value: '',      label: 'Все' },
  { value: 'true',  label: 'Активен' },
  { value: 'false', label: 'Заблокирован' },
];

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

      <Select
        style={{ minWidth: 160 }}
        value={filters.role}
        options={ROLE_OPTIONS}
        onChange={(val) => onFiltersChange({ ...filters, role: val })}
        placeholder="Все роли"
      />

      <Select
        style={{ minWidth: 140 }}
        value={filters.is_active}
        options={STATUS_OPTIONS}
        onChange={(val) => onFiltersChange({ ...filters, is_active: val })}
        placeholder="Все"
      />

      <Checkbox
        checked={filters.includeDeleted}
        onChange={() => onFiltersChange({ ...filters, includeDeleted: !filters.includeDeleted })}
        label="Показать удалённых"
      />
    </div>
  );
}
