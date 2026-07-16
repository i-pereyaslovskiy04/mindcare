/**
 * Multi-role helpers (ADR-018) — единая точка чтения ролей на фронте.
 *
 * Источник прав доступа — набор активных ролей `roles: Role[]` (backend
 * возвращает его в login/me/profile и в admin users list/read/create). Legacy
 * `role` — только convenience/primary для обратной совместимости; НЕ источник
 * авторизации. Переключение кабинета — UI-only; membership всё равно проверяет
 * backend (`require_role`).
 */

// Детерминированный приоритет ролей (default cabinet / primary).
export const ROLE_PRIORITY = ['admin', 'supervisor', 'psychologist', 'student'];

const _PRIORITY_INDEX = ROLE_PRIORITY.reduce((acc, name, i) => {
  acc[name] = i;
  return acc;
}, {});

/**
 * Нормализует роли из user/item в детерминированный массив.
 *
 * Правила:
 *   - явный `roles` (массив, даже пустой `[]`) — источник истины;
 *   - legacy fallback `[role]` — ТОЛЬКО при полном отсутствии поля `roles`
 *     (не при пустом массиве);
 *   - неизвестные роли отбрасываются, дубликаты убираются, порядок — по
 *     ROLE_PRIORITY.
 */
export function normalizeRoles(source) {
  if (!source) return [];

  let raw;
  if (Array.isArray(source.roles)) {
    raw = source.roles; // explicit roles[] — source of truth (even [])
  } else if (source.role) {
    raw = [source.role]; // legacy fallback: only when `roles` field is absent
  } else {
    raw = [];
  }

  const seen = new Set();
  const cleaned = [];
  for (const r of raw) {
    if (_PRIORITY_INDEX[r] === undefined) continue; // drop unknown roles
    if (seen.has(r)) continue; // dedupe
    seen.add(r);
    cleaned.push(r);
  }
  cleaned.sort((a, b) => _PRIORITY_INDEX[a] - _PRIORITY_INDEX[b]);
  return cleaned;
}

/**
 * Primary/default роль по глобальному приоритету, или null для пустого набора.
 * НЕ маскирует отсутствие ролей как 'student'.
 */
export function primaryRole(roles) {
  const list = Array.isArray(roles) ? roles : normalizeRoles(roles);
  for (const name of ROLE_PRIORITY) {
    if (list.includes(name)) return name;
  }
  return null;
}

// Канонические подписи и тон Badge ролей — единый источник для лейблов кабинетов,
// профиля и switcher/chooser (сводит прежнее расхождение «Пациент»/«Студент»).
export const ROLE_LABELS = {
  student:      'Студент',
  psychologist: 'Психолог',
  supervisor:   'Супервизор',
  admin:        'Администратор',
};

export const ROLE_BADGE_TONES = {
  student:      'role-student',
  psychologist: 'role-psychologist',
  supervisor:   'role-supervisor',
  admin:        'role-admin',
};

export const roleLabel = (role) => ROLE_LABELS[role] ?? role ?? '';
