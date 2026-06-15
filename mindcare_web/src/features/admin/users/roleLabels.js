/**
 * Общие подписи и тон Badge для ролей пользователей.
 * Переиспользуются в UsersTable, UserEditModal (Select роли) и UserCreateModal.
 */

export const ROLE_LABELS = {
  student:      'Студент',
  psychologist: 'Психолог',
  admin:        'Администратор',
  supervisor:   'Супервизор',
};

export const ROLE_BADGE_TONES = {
  student:      'role-student',
  psychologist: 'role-psychologist',
  admin:        'role-admin',
  supervisor:   'role-supervisor',
};

/**
 * Роли, требующие документированного основания (legal basis) при назначении —
 * как при создании пользователя, так и при смене роли через edit-форму.
 * Должны совпадать с backend-политикой (Stage 31f-fix).
 */
export const STAFF_ROLES = ['psychologist', 'supervisor', 'admin'];

export function isStaffRole(role) {
  return STAFF_ROLES.includes(role);
}

/**
 * Selectable роли для edit-формы админки — только staff/admin.
 * «Студент» НЕ предлагается: студенты появляются через self-registration,
 * админ не назначает роль student через dropdown (Stage 31n-hotfix).
 * Текущая роль student у редактируемого пользователя отображается через
 * Select `displayLabel` (ROLE_LABELS), но недоступна для выбора.
 */
export const EDIT_ROLE_OPTIONS = [
  { value: 'psychologist', label: ROLE_LABELS.psychologist },
  { value: 'supervisor',   label: ROLE_LABELS.supervisor },
  { value: 'admin',        label: ROLE_LABELS.admin },
];

/**
 * Опции роли для create-формы — только staff/admin.
 * Студент создаётся публичной регистрацией, не через админку.
 */
export const CREATE_ROLE_OPTIONS = [
  { value: 'supervisor',   label: ROLE_LABELS.supervisor },
  { value: 'psychologist', label: ROLE_LABELS.psychologist },
  { value: 'admin',        label: ROLE_LABELS.admin },
];
