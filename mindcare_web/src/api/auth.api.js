/**
 * Auth API — all /api/auth/* calls.
 *
 * Every function goes through apiFetch (client.js).
 * No raw fetch() anywhere in this file.
 *
 * Public endpoints (no auth required): login, registerInit,
 * registerConfirm, passwordResetInit, passwordResetConfirm, oauthStart,
 * oauthComplete, oauthRegistrationPreview, oauthRegistrationInit,
 * oauthRegistrationConfirm.
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

/**
 * GET /api/auth/profile
 * → { id, email, full_name, phone, role, ui_theme_palette, ui_theme_mode }
 * Поля темы могут быть null — «не задано» (действует выбор устройства).
 */
export function getProfile() {
  return apiFetch(`${BASE}/profile`);
}

/**
 * PATCH /api/auth/profile — частичное обновление self-полей.
 * Отправляются только переданные ключи (backend: unset ≠ null).
 * Допустимые: full_name, phone, ui_theme_palette, ui_theme_mode.
 */
export function updateProfile(fields) {
  return apiFetch(`${BASE}/profile`, {
    method: 'PATCH',
    body: JSON.stringify(fields),
  });
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

/**
 * POST /api/auth/account/deactivate — самоотключение (ADR-028). Только для
 * студенческого аккаунта; target — текущий пользователь (id не передаётся).
 * Все сессии отзываются — после успеха клиент очищает авторизацию.
 */
export function deactivateOwnAccount() {
  return apiFetch(`${BASE}/account/deactivate`, {
    method: 'POST',
    body: JSON.stringify({ confirm: true }),
  });
}

/** POST /api/auth/change-password — changes password for the authenticated user.
 *  Revokes all sessions including current; client must logout after success. */
export function changePassword({ current_password, new_password, new_password_confirm }) {
  return apiFetch(`${BASE}/change-password`, {
    method: 'POST',
    body: JSON.stringify({ current_password, new_password, new_password_confirm }),
  });
}

/**
 * POST /api/auth/oauth/{provider}/start → { authorize_url }  (Stage Social Auth 3B)
 *
 * Backend ставит HttpOnly state-cookie (Path=/api/auth/oauth), привязывающий
 * вход к этому браузеру. `credentials: 'include'` — только здесь (не в
 * глобальном apiFetch): в same-origin dev он ничего не меняет, а при SPA/API на
 * разных поддоменах одного сайта без него cookie не сохранится.
 */
export function oauthStart(provider) {
  return apiFetch(`${BASE}/oauth/${encodeURIComponent(provider)}/start`, {
    method: 'POST',
    credentials: 'include',
  });
}

/**
 * POST /api/auth/oauth/complete { ticket } → SessionResponse (как у login).
 * Ticket одноразовый; ошибки — 400/403/429 с полем `code`, но не 401.
 */
export function oauthComplete(ticket) {
  return apiFetch(`${BASE}/oauth/complete`, {
    method: 'POST',
    body: JSON.stringify({ ticket }),
  });
}

/**
 * POST /api/auth/oauth/registration/preview { ticket }
 * → { provider, email_masked | null, email_allowed, email_editable }
 * (Stage Social Auth VK-1B). Что показать на шаге email: маскированный адрес,
 * привязанный к ticket, и можно ли с ним продолжить. Ничего не меняет и код
 * не отправляет. Raw email backend не отдаёт.
 */
export function oauthRegistrationPreview({ ticket }) {
  return apiFetch(`${BASE}/oauth/registration/preview`, {
    method: 'POST',
    body: JSON.stringify({ ticket }),
  });
}

/**
 * POST /api/auth/oauth/registration/init { ticket[, email] }
 * → { message, email_masked }  (Stage Social Auth 4 / VK-1B).
 * Без email — код уходит на адрес, уже привязанный к ticket (Яндекс: адрес
 * профиля; VK: адрес VK или ранее выбранный; повтор — повторная отправка,
 * cooldown 60 с). С email — только для VK: адрес, который пользователь указал
 * сам; backend проверяет домен и занятость и отправляет код на него. Имя
 * клиент не передаёт никогда.
 */
export function oauthRegistrationInit({ ticket, email }) {
  const body = { ticket };
  if (typeof email === 'string' && email) body.email = email;
  return apiFetch(`${BASE}/oauth/registration/init`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/**
 * POST /api/auth/oauth/registration/confirm
 * { ticket, code, consent_accepted: true } → SessionResponse.
 * Создаёт аккаунт без пароля, привязку провайдера и обычную сессию MindCare.
 * consent_accepted — согласие MindCare; backend принимает только true.
 */
export function oauthRegistrationConfirm({ ticket, code, consentAccepted }) {
  return apiFetch(`${BASE}/oauth/registration/confirm`, {
    method: 'POST',
    body: JSON.stringify({ ticket, code, consent_accepted: consentAccepted === true }),
  });
}
