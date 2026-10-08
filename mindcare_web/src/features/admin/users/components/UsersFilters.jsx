import Select from '../../../../components/UI/Select/Select';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import { ROLE_LABELS } from '../roleLabels';
import styles from './UsersFilters.module.css';

// Подписи ролей — из общей карты (shared/lib/roles.js через ../roleLabels):
// локальных копий нет, подпись «Пользователь» меняется в одном месте.
const ROLE_OPTIONS = [
  { value: '',             label: 'Все роли' },
  { value: 'student',      label: ROLE_LABELS.student },
  { value: 'psychologist', label: ROLE_LABELS.psychologist },
  { value: 'admin',        label: ROLE_LABELS.admin },
  { value: 'supervisor',   label: ROLE_LABELS.supervisor },
];

// ADR-028: «Отключён» включает и ранее удалённые аккаунты (backend добавляет
// их сам при is_active=false) — их тоже восстанавливает администратор.
const STATUS_OPTIONS = [
  { value: '',      label: 'Все' },
  { value: 'true',  label: 'Активен' },
  { value: 'false', label: 'Отключён' },
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
        label="Показать ранее удалённых"
      />
    </div>
  );
}
