/**
 * Действия над строкой /admin/users — единая матрица для таблицы и
 * компактного списка (оба представления строят кнопки только отсюда).
 * Правила прежние, backend дублирует guard'ы (defense-in-depth):
 *   - удалённый ранее (deleted_at) — только «Восстановить»;
 *   - отключённый — «Редактировать» и «Восстановить»;
 *   - «Зайти под именем» — активный не-админ и не сам админ (ADR-025);
 *   - «Отключить аккаунт» — активный и не свой (422 self_admin_protected,
 *     ADR-028): действие не показывается вовсе.
 */

/** Отключён = is_active=false ИЛИ исторически soft-deleted (ADR-028). */
export function isDisabled(item) {
  return Boolean(item.deleted_at) || item.is_active === false;
}

export function canImpersonate(item, currentUserId) {
  return !isDisabled(item)
    && !(item.roles || []).includes('admin')
    && item.id !== currentUserId;
}

export function canDeactivate(item, currentUserId) {
  return !isDisabled(item) && item.id !== currentUserId;
}

/**
 * { primary, menu } — основное действие (видно всегда) и остальные (в меню).
 * Основное — «Редактировать», у удалённого ранее — «Восстановить».
 * Пока идёт вход под именем (pendingImpersonation), этот пункт недоступен.
 */
export function getUserActions(item, {
  currentUserId, pendingImpersonation = false,
  onEdit, onDeactivate, onRestore, onImpersonate,
}) {
  const name = item.full_name;
  const edit = !item.deleted_at && {
    id: 'edit', label: 'Редактировать', ariaLabel: `Редактировать ${name}`,
    onSelect: () => onEdit?.(item),
  };
  const restore = isDisabled(item) && {
    id: 'restore', label: 'Восстановить', ariaLabel: `Восстановить ${name}`, tone: 'success',
    onSelect: () => onRestore?.(item),
  };
  const impersonate = canImpersonate(item, currentUserId) && {
    id: 'impersonate', label: 'Зайти под именем', disabled: pendingImpersonation,
    onSelect: () => onImpersonate?.(item),
  };
  const deactivate = canDeactivate(item, currentUserId) && {
    id: 'deactivate', label: 'Отключить аккаунт', tone: 'danger',
    onSelect: () => onDeactivate?.(item),
  };

  const primary = edit || restore || null;
  const menu = [impersonate, primary === restore ? null : restore, deactivate].filter(Boolean);
  return { primary, menu };
}
