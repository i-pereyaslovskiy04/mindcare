import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
} from 'react';
import { configureClient } from '../../api/client';

const AuthContext = createContext(null);

const AUTH_BASE = '/api/auth';

async function _post(url, body, token = null) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: body !== null ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || data.message || `HTTP ${res.status}`);
  }
  return res.json();
}

async function _getMe(sessionToken) {
  const res = await fetch(`${AUTH_BASE}/me`, {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${sessionToken}`,
    },
  });
  if (!res.ok) throw new Error('Failed to fetch user');
  return res.json();
}

export const authApi = {
  register:             (body) => _post(`${AUTH_BASE}/register`, body),
  registerInit:         (body) => _post(`${AUTH_BASE}/register/init`, body),
  registerConfirm:      (body) => _post(`${AUTH_BASE}/register/confirm`, body),
  login:                (body) => _post(`${AUTH_BASE}/login`, body),
  logout:               (token) => _post(`${AUTH_BASE}/logout`, null, token),
  passwordResetInit:    (body) => _post(`${AUTH_BASE}/password/reset/init`, body),
  passwordResetConfirm: (body) => _post(`${AUTH_BASE}/password/reset/confirm`, body),
  me: _getMe,
};

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [loading, setLoading] = useState(true);
  const sessionTokenRef       = useRef(null);

  const getToken = useCallback(() => sessionTokenRef.current, []);

  useEffect(() => {
    configureClient({ getToken });
  }, [getToken]);

  const clearSession = useCallback(() => {
    sessionTokenRef.current = null;
    localStorage.removeItem('session_token');
    setUser(null);
  }, []);

  // Слушаем событие "сессия истекла" от apiFetch
  useEffect(() => {
    const handler = () => clearSession();
    window.addEventListener('auth:session-expired', handler);
    return () => window.removeEventListener('auth:session-expired', handler);
  }, [clearSession]);

  // Восстановление сессии при перезагрузке страницы
  useEffect(() => {
    let cancelled = false;

    const restore = async () => {
      const storedToken = localStorage.getItem('session_token');
      if (!storedToken) {
        if (!cancelled) setLoading(false);
        return;
      }

      try {
        sessionTokenRef.current = storedToken;
        const userData = await authApi.me(storedToken);
        if (!cancelled) setUser(userData);
      } catch {
        // Сессия недействительна — чистим
        if (!cancelled) {
          sessionTokenRef.current = null;
          localStorage.removeItem('session_token');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    restore();
    return () => { cancelled = true; };
  }, []);

  const login = useCallback(async ({ email, password }) => {
    // Ответ: { session_token, expires_at, role }
    const data = await authApi.login({ email, password });
    sessionTokenRef.current = data.session_token;
    localStorage.setItem('session_token', data.session_token);
    const userData = await authApi.me(data.session_token);
    setUser(userData);
    return data.role;
  }, []);

  const logout = useCallback(async () => {
    const token = sessionTokenRef.current;
    if (token) {
      try { await authApi.logout(token); } catch {}
    }
    clearSession();
  }, [clearSession]);

  const value = {
    user,
    loading,
    isAuthenticated: !!user,
    login,
    logout,
    getToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
