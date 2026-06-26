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

const SESSION_KEY = 'mindcare_session';

function getStoredToken() {
  return localStorage.getItem(SESSION_KEY);
}
function setStoredToken(token) {
  localStorage.setItem(SESSION_KEY, token);
}
function clearStoredToken() {
  localStorage.removeItem(SESSION_KEY);
}

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [loading, setLoading] = useState(true);
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

  // ── Session-expired event (fired by apiFetch on 401) ─────────────────────

  const _clearSession = useCallback(() => {
    _clearToken();
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
        if (!cancelled) setLoading(false);
        return;
      }

      tokenRef.current = stored; // must be set BEFORE calling me()
      try {
        const userData = await authApi.me();
        if (!cancelled) setUser(userData);
      } catch {
        // Session invalid or expired — clear it.
        if (!cancelled) _clearToken();
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    restore();
    return () => { cancelled = true; };
  }, []);

  // ── Actions ───────────────────────────────────────────────────────────────

  const login = useCallback(async ({ email, password }) => {
    const data = await authApi.login({ email, password });
    _saveToken(data.session_token);

    const userData = await authApi.me();
    // flushSync: user state must be committed before the caller's navigate()
    // fires, otherwise ProtectedRoute sees user=null and redirects to /.
    flushSync(() => { setUser(userData); });

    return data.role;
  }, []);

  const logout = useCallback(async () => {
    try { await authApi.logout(); } catch { /* fire-and-forget */ }
    _clearSession();
  }, [_clearSession]);

  /** Re-fetch /me и обновить user (например, после смены профиля). */
  const refreshUser = useCallback(async () => {
    const userData = await authApi.me();
    setUser(userData);
    return userData;
  }, []);

  const value = {
    user,
    loading,
    isAuthenticated: !!user,
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
