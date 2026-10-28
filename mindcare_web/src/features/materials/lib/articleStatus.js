// Статусы модерации статей (ADR-034) — подписи и тона как у модерации тестов.
export const ARTICLE_STATUS_LABELS = {
  draft:         'Черновик',
  in_review:     'На проверке',
  needs_changes: 'На доработке',
  published:     'Опубликовано',
};

export const ARTICLE_STATUS_TONES = {
  draft:         'neutral',
  in_review:     'warning',
  needs_changes: 'error',
  published:     'success',
};

/** Статус статьи; старые ответы без поля status — по is_published. */
export function articleStatus(item) {
  return item?.status || (item?.is_published ? 'published' : 'draft');
}
