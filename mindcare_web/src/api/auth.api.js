/**
 * Auth API — all /api/auth/* calls.
 *
 * Every function goes through apiFetch (client.js).
 * No raw fetch() anywhere in this file.
 *
 * Public endpoints (no auth required): login, registerInit,
 * registerConfirm, passwordResetInit, passwordResetConfirm.
 *
 * Protected endpoints (requires Bearer token in client): me, logout.
 */

import { apiFetch } from './client';

const BASE = '/api/auth';

/** POST /api/auth/login → { session_token, expires_at, role } */
export function login({ email, password }) {
  return apiFetch(`${BASE}/login`, {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

/** POST /api/auth/logout — revokes current session. */
export function logout() {
  return apiFetch(`${BASE}/logout`, { method: 'POST' });
}

/** GET /api/auth/me → { id, email, name, role } */
export function me() {
  return apiFetch(`${BASE}/me`);
}

/** POST /api/auth/register/init — sends OTP to email. */
export function registerInit({ name, email, password }) {
  return apiFetch(`${BASE}/register/init`, {
    method: 'POST',
    body: JSON.stringify({ name, email, password }),
  });
}

/** POST /api/auth/register/confirm — verifies OTP, creates account. */
export function registerConfirm({ email, code }) {
  return apiFetch(`${BASE}/register/confirm`, {
    method: 'POST',
    body: JSON.stringify({ email, code }),
  });
}

/** POST /api/auth/password/reset/init — sends reset OTP (silent if email not found). */
export function passwordResetInit({ email }) {
  return apiFetch(`${BASE}/password/reset/init`, {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

/** POST /api/auth/password/reset/confirm — verifies OTP + sets new password. */
export function passwordResetConfirm({ email, code, new_password }) {
  return apiFetch(`${BASE}/password/reset/confirm`, {
    method: 'POST',
    body: JSON.stringify({ email, code, new_password }),
  });
}
