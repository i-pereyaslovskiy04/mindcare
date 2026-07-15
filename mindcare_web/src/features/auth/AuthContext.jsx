/**
 * AuthContext — session state and auth actions.
 *
 * Token lifecycle:
 *   - Stored in memory (React ref) for synchronous access.
 *   - Also persisted to localStorage so the session survives page reloads
 *     and is shared across tabs (MVP convenience).
 *   - Production-grade alternative: HttpOnly Secure SameSite cookie + CSRF
 *     (eliminates XSS token theft risk) — kept as a future stage.
 *   - Backend sessions are server-side and can be revoked on logout /
 *     change-password regardless of storage mechanism.
 *
 * All HTTP calls go through api/auth.api.js → api/client.js.
 * No raw fetch() in this file.
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
} from 'react';
import { flushSync } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { configureClient } from '../../api/client';
import * as authApi from '../../api/auth.api';
import { normalizeRoles } from '../../shared/lib/roles';

const SESSION_KEY = 'mindcare_session';
const ACTIVE_ROLE_KEY = 'mindcare_active_role';

function getStoredToken() {
  return localStorage.getItem(SESSION_KEY);
}
function setStoredToken(token) {
  localStorage.setItem(SESSION_KEY, token);
}
function clearStoredToken() {
  localStorage.removeItem(SESSION_KEY);
}
function getStoredActiveRole() {
  return localStorage.getItem(ACTIVE_ROLE_KEY);
}
function setStoredActiveRole(role) {
  localStorage.setItem(ACTIVE_ROLE_KEY, role);
}
function clearStoredActiveRole() {
  localStorage.removeItem(ACTIVE_ROLE_KEY);
}

/**
 * Единая нормализация auth-user (ADR-018): гарантирует `roles: Role[]` как
 * источник истины. Явный backend `roles` (даже []) сохраняется; legacy `role`
 * даёт fallback `[role]` только при полном отсутствии поля `roles`.
 */
function normalizeUser(raw) {
  if (!raw) return null;
  return { ...raw, roles: normalizeRoles(raw) };
}

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [loading, setLoading] = useState(true);
  // activeRole — UI-hint выбранного кабинета (не право доступа). Ленивая
  // инициализация из localStorage, чтобы валидный сохранённый кабинет был
  // доступен на первом рендере после loading=false (без вспышки RoleChooser).
  const [activeRole, setActiveRoleState] = useState(() => getStoredActiveRole());
  const tokenRef              = useRef(null);
  const navigate              = useNavigate();

  /** Expose token to the HTTP client. */
  const getToken = useCallback(() => tokenRef.current, []);

  useEffect(() => {
    configureClient({ getToken });
  }, [getToken]);

  // ── Helpers ───────────────────────────────────────────────────────────────

  const _saveToken = (token) => {
    tokenRef.current = token;
    setStoredToken(token);
  };

  const _clearToken = () => {
    tokenRef.current = null;
    clearStoredToken();
  };

  const _clearActiveRole = () => {
    setActiveRoleState(null);
    clearStoredActiveRole();
  };

  // ── Session-expired event (fired by apiFetch on 401) ─────────────────────

  const _clearSession = useCallback(() => {
    _clearToken();
    _clearActiveRole();
    setUser(null);
  }, []);

  useEffect(() => {
    const currentUser = user;
    const handler = () => {
      if (currentUser) {
        // User was logged in — navigate to home with login modal + message
        navigate('/', {
          replace: true,
          state: { openAuth: 'login', message: 'Сессия истекла. Войдите снова.' },
        });
      }
      _clearSession();
    };
    window.addEventListener('auth:session-expired', handler);
    return () => window.removeEventListener('auth:session-expired', handler);
  }, [_clearSession, user, navigate]);

  // ── Restore session on page load ──────────────────────────────────────────

  useEffect(() => {
    let cancelled = false;

    async function restore() {
      const stored = getStoredToken();
      if (!stored) {
        // Нет сессии — сбрасываем и activeRole, иначе выбор кабинета «протекает»
        // между разными пользователями на одном устройстве.
        if (!cancelled) {
          _clearActiveRole();
          setLoading(false);
        }
        return;
      }

      tokenRef.current = stored; // must be set BEFORE calling me()
      try {
        const userData = await authApi.me();
        if (!cancelled) setUser(normalizeUser(userData));
      } catch {
        // Session invalid or expired — clear it (token + activeRole).
        if (!cancelled) {
          _clearToken();
          _clearActiveRole();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    restore();
    return () => { cancelled = true; };
  }, []);

  // ── Reconcile activeRole against membership ───────────────────────────────
  // Сохранённый/выбранный activeRole действителен только пока роль в user.roles.
  useEffect(() => {
    if (!user) return;
    if (activeRole && !normalizeRoles(user).includes(activeRole)) {
      _clearActiveRole();
    }
  }, [user, activeRole]);

  // ── Actions ───────────────────────────────────────────────────────────────

  const login = useCallback(async ({ email, password }) => {
    const data = await authApi.login({ email, password });
    _saveToken(data.session_token);

    const userData = await authApi.me();
    // flushSync: user state must be committed before the caller's navigate()
    // fires, otherwise ProtectedRoute sees user=null and redirects to /.
    flushSync(() => { setUser(normalizeUser(userData)); });

    // Кабинет выбирает DashboardRedirect — caller навигирует на /dashboard,
    // а не по одной legacy-роли.
    return normalizeUser(userData);
  }, []);

  const logout = useCallback(async () => {
    try { await authApi.logout(); } catch { /* fire-and-forget */ }
    _clearSession();
  }, [_clearSession]);

  /** Re-fetch /me и обновить user (например, после смены профиля). */
  const refreshUser = useCallback(async () => {
    const userData = await authApi.me();
    const normalized = normalizeUser(userData);
    setUser(normalized);
    // Если текущий activeRole больше не назначен — сбросить (reconcile-эффект
    // тоже сработает, но делаем явно и синхронно к обновлению user).
    if (activeRole && !normalized.roles.includes(activeRole)) {
      _clearActiveRole();
    }
    return normalized;
  }, [activeRole]);

  /** UI-hint выбора кабинета. Принимает роль только из текущего user.roles. */
  const setActiveRole = useCallback((role) => {
    if (!normalizeRoles(user).includes(role)) return; // reject non-member
    setActiveRoleState(role);
    setStoredActiveRole(role);
  }, [user]);

  const value = {
    user,
    loading,
    isAuthenticated: !!user,
    activeRole,
    setActiveRole,
    login,
    logout,
    refreshUser,
    getToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

/**
 * useLogout — единая logout-функция для всех кабинетов.
 *
 * Сначала навигирует на `/`, потом очищает сессию.
 * Порядок важен: если сначала очистить сессию, RoleRoute успевает
 * отредиректить на /login до того, как сработает наш navigate('/').
 */
export function useLogout() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  return useCallback(async () => {
    navigate('/', { replace: true });
    await logout();
  }, [logout, navigate]);
}
