/**
 * Public config API — GET /api/public/config (без авторизации).
 *
 * Сейчас фронтенду отсюда нужен только `social_providers` (Stage Social Auth
 * 3B): имена провайдеров, которые backend реально зарегистрировал. ClientID,
 * URL и прочая конфигурация провайдеров сюда не приходят.
 */

import { apiFetch } from './client';

/** GET /api/public/config → { social_providers: string[], ... } */
export function getPublicConfig() {
  return apiFetch('/api/public/config');
}

/**
 * Безопасно извлекает список провайдеров: всё, что не массив строк, — пустой
 * список (кнопки входа не показываются).
 */
export function socialProvidersOf(config) {
  const list = config?.social_providers;
  if (!Array.isArray(list)) return [];
  return list.filter((name) => typeof name === 'string');
}
