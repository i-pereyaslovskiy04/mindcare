/**
 * Действия над строкой /supervisor/engagements — единая матрица для всех
 * раскладок ResponsiveTable. Правила прежние:
 *   - нет активной связи — «Назначить» (основное);
 *   - есть активная связь — «Переназначить» (основное) и «Закрыть связь»;
 *   - «Результаты» и «Контакты» — всегда (только чтение; чтение контактов
 *     фиксируется в журнале при открытии диалога, ADR-032).
 * Основное действие — кнопкой, остальные — в меню «⋮».
 */
export function getEngagementActions(student, {
  onAssign, onTransfer, onClose, onResults, onContacts,
}) {
  const name = student.full_name;
  const hasEngagement = Boolean(student.current_engagement);

  const primary = hasEngagement
    ? { id: 'transfer', label: 'Переназначить', ariaLabel: `Переназначить: ${name}`,
      onSelect: () => onTransfer?.(student) }
    : { id: 'assign', label: 'Назначить', ariaLabel: `Назначить: ${name}`, variant: 'primary',
      onSelect: () => onAssign?.(student) };

  const menu = [
    { id: 'results', label: 'Результаты тестов', onSelect: () => onResults?.(student) },
    { id: 'contacts', label: 'Контакты', onSelect: () => onContacts?.(student) },
    hasEngagement && {
      id: 'close', label: 'Закрыть связь', tone: 'danger', onSelect: () => onClose?.(student),
    },
  ].filter(Boolean);

  return { primary, menu };
}
