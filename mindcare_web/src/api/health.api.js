/**
 * Health API — GET /api/health
 *
 * Returns DB status, table count, and current Alembic revision.
 * Used by the /health debug page.
 */

import { apiFetch } from './client';

/** GET /api/health → { status, db, tables, revision } */
export function getHealth() {
  return apiFetch('/api/health');
}
