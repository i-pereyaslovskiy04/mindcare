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

/**
 * Фильтры /admin/users. Видимость аккаунтов задаёт ОДИН контрол — галочка
 * «Показать отключённых» (ADR-028): без неё — только активные, с ней —
 * активные и отключённые, в т.ч. ранее удалённые. Отдельного селектора
 * статуса нет, чтобы два контрола не задавали конфликтующие условия.
 * Параметры API собирает useAdminUsers.
 */
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

      <Checkbox
        checked={filters.showDisabled}
        onChange={() => onFiltersChange({ ...filters, showDisabled: !filters.showDisabled })}
        label="Показать отключённых"
      />
    </div>
  );
}
