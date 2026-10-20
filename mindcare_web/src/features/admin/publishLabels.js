/**
 * UI-тексты для публикации в формах новостей/статей.
 *
 * Только текст: payload is_published работает как раньше, будущая дата
 * публикацию не откладывает (никакого scheduling).
 */

// Чекбокс всегда подписан действием/флагом «Опубликовать».
// Итоговое состояние (черновик/публикация) подсказывает submitButtonLabel.
export function publishCheckboxLabel() {
  return 'Опубликовать';
}

export function submitButtonLabel({ isEdit, isPublished, submitting }) {
  if (submitting) return 'Сохранение…';
  if (isEdit) {
    return isPublished ? 'Сохранить и опубликовать' : 'Сохранить как черновик';
  }
  return isPublished ? 'Создать и опубликовать' : 'Сохранить черновик';
}
