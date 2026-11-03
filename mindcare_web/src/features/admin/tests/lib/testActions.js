/**
 * Действия над строкой списка тестов — единая матрица для всех раскладок
 * ResponsiveTable и всех кабинетов. Правила прежние (Этапы F1, F2, F2.1):
 *
 * context 'moderator' — /admin/tests и /supervisor/tests (backend разрешает обе
 * роли одинаково):
 *   - «Опубликовать» — любой статус, кроме published;
 *   - «Вернуть на доработку» — только in_review (диалог с комментарием);
 *   - «Предпросмотр», «Скрыть из каталога» / «Показать в каталоге»,
 *     «Редактировать», «Удалить» — всегда (видимость статусом не гейтится:
 *     до публикации is_active ни на что не влияет).
 *
 * context 'author' — /psychologist/tests (только свои тесты):
 *   - «Отправить на модерацию» — draft и needs_changes;
 *   - «Предпросмотр» — всегда;
 *   - «Редактировать» — draft, needs_changes и published (правка published
 *     снимает его с публикации — предупреждение показывает страница);
 *   - «Удалить» — draft и needs_changes. На проверке (in_review) решение не
 *     за автором (ADR-016): ни правки, ни удаления.
 *
 * Основное действие — кнопкой, остальные — в меню «⋮»:
 *   moderator: in_review — «Опубликовать» (решение по очереди модерации),
 *              иначе «Редактировать»;
 *   author:    draft / needs_changes — «Редактировать»; in_review и
 *              published — «Предпросмотр» (правка published снимает
 *              публикацию, поэтому она не основное действие).
 *
 * pending — { [actionId]: uuid } выполняющихся действий: у этой строки
 * действие недоступно (повторно не отправить), у других строк — доступно.
 */
export const AUTHOR_EDITABLE_STATUSES = ['draft', 'needs_changes', 'published'];
export const AUTHOR_DELETABLE_STATUSES = ['draft', 'needs_changes'];

export function getTestActions(test, {
  context, pending = {},
  onPreview, onEdit, onDelete, onPublish, onReturn, onSubmitForReview, onToggleActive,
}) {
  const { status } = test;
  const isModerator = context === 'moderator';
  const isAuthor = context === 'author';
  const action = (id, label, handler, extra = {}) => handler && {
    id, label, onSelect: () => handler(test), disabled: pending[id] === test.uuid, ...extra,
  };

  const all = [
    isModerator && status !== 'published' && action('publish', 'Опубликовать', onPublish, { tone: 'success' }),
    isModerator && status === 'in_review' && action('return', 'Вернуть на доработку', onReturn),
    isAuthor && (status === 'draft' || status === 'needs_changes')
      && action('submit', 'Отправить на модерацию', onSubmitForReview, { tone: 'success' }),
    action('preview', 'Предпросмотр', onPreview),
    isModerator && (test.is_active
      ? action('toggle', 'Скрыть из каталога', onToggleActive, { tone: 'danger' })
      : action('toggle', 'Показать в каталоге', onToggleActive, { tone: 'success' })),
    (isModerator || (isAuthor && AUTHOR_EDITABLE_STATUSES.includes(status)))
      && action('edit', 'Редактировать', onEdit),
    (isModerator || (isAuthor && AUTHOR_DELETABLE_STATUSES.includes(status)))
      && action('delete', 'Удалить', onDelete, { tone: 'danger' }),
  ].filter(Boolean);

  let primaryId;
  if (isModerator) primaryId = status === 'in_review' ? 'publish' : 'edit';
  else primaryId = status === 'draft' || status === 'needs_changes' ? 'edit' : 'preview';

  const found = all.find((a) => a.id === primaryId) || null;
  const primary = found && { ...found, variant: found.id === 'publish' ? 'primary' : 'secondary' };
  return { primary, menu: all.filter((a) => a !== found) };
}
