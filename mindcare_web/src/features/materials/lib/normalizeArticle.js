// Нормализация статьи публичного API (/api/articles) для карточек библиотеки.
// Только реальные поля ответа: времени чтения у статьи нет и не выдумывается.

const DATE_FORMAT = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Europe/Moscow',
});

export function formatMaterialDate(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : DATE_FORMAT.format(date);
}

export function normalizeArticle(item) {
  const categories = Array.isArray(item.categories) ? item.categories : [];
  const tags       = Array.isArray(item.tags) ? item.tags : [];
  return {
    id:          item.uuid,
    title:       item.title,
    description: item.excerpt || '',
    date:        formatMaterialDate(item.published_at || item.created_at),
    dateTime:    item.published_at || item.created_at || null,
    image:       item.cover_image_url || null,
    category:    categories[0]?.name || '',
    topics:      tags.map(t => t.name).filter(Boolean),
  };
}
