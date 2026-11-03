/**
 * Health API.
 *
 * Публичный GET /api/health — только {status} для мониторинга (не для UI).
 * Подробная диагностика — GET /api/admin/health, только admin: ревизия и head
 * Alembic, число таблиц; при сбое — только класс исключения.
 */

import { apiFetch } from './client';

/** GET /api/admin/health → { status, db, revision, head_revisions, revision_ok, tables } */
export function getAdminHealth() {
  return apiFetch('/api/admin/health');
}
