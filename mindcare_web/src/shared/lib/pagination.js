/**
 * Серверная пагинация: коррекция страницы, когда текущая опустела (запись
 * отключена, решена другим пользователем, исчезла между запросами).
 *
 *   lastPage = max(1, ceil(total / size));
 *   страница > 1 и пуста → max(1, min(lastPage, page - 1)).
 *
 * total = 0 → 1. Если total ещё «видит» записи, а страница пуста (count и
 * страница прочитаны в разные моменты), — шаг назад: номер страницы строго
 * убывает, зацикливания нет. Непустая страница и страница 1 не меняются.
 */
export function lastPageOf(total, size) {
  return Math.max(1, Math.ceil((Number(total) || 0) / size));
}

export function correctedPage(page, size, itemsCount, total) {
  if (page <= 1 || itemsCount > 0) return page;
  return Math.max(1, Math.min(lastPageOf(total, size), page - 1));
}
