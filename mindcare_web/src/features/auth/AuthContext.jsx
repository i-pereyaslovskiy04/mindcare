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

async function _post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || data.message || `HTTP ${res.status}`);
  }
  return res.json();
}

async function _getMe(accessToken) {
  const res = await fetch(`${AUTH_BASE}/me`, {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!res.ok) throw new Error('Failed to fetch user');
  return res.json();
}

export const authApi = {
  register:             (body)  => _post(`${AUTH_BASE}/register`, body),
  registerInit:         (body)  => _post(`${AUTH_BASE}/register/init`, body),
  registerConfirm:      (body)  => _post(`${AUTH_BASE}/register/confirm`, body),
  login:                (body)  => _post(`${AUTH_BASE}/login`, body),
  refresh:              (token) => _post(`${AUTH_BASE}/refresh`, { refresh_token: token }),
  logout:               (token) => _post(`${AUTH_BASE}/logout`, { refresh_token: token }),
  passwordResetInit:    (body)  => _post(`${AUTH_BASE}/password/reset/init`, body),
  passwordResetConfirm: (body)  => _post(`${AUTH_BASE}/password/reset/confirm`, body),
  me: _getMe,
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const accessTokenRef = useRef(null);

  const getToken = useCallback(() => accessTokenRef.current, []);
  const setToken = useCallback((token) => { accessTokenRef.current = token; }, []);

  useEffect(() => {
    configureClient({ getToken, setToken });
  }, [getToken, setToken]);

  const clearSession = useCallback(() => {
    accessTokenRef.current = null;
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('access_token');
    setUser(null);
  }, []);

  useEffect(() => {
    const handler = () => clearSession();
    window.addEventListener('auth:session-expired', handler);
    return () => window.removeEventListener('auth:session-expired', handler);
  }, [clearSession]);

  // Restore session on mount.
  // Strategy: try the stored access_token first (fast, no rotation).
  // Only fall back to refresh when it is expired/missing.
  // Cancellation flag prevents StrictMode's double-invoke from causing
  // two concurrent rotations with the same refresh token.
  useEffect(() => {
    let cancelled = false;

    const restore = async () => {
      const storedAccess = localStorage.getItem('access_token');

      if (storedAccess) {
        try {
          accessTokenRef.current = storedAccess;
          const userData = await authApi.me(storedAccess);
          if (!cancelled) {
            setUser(userData);
            setLoading(false);
          }
          return;
        } catch {
          // Token expired or invalid — fall through to refresh.
          accessTokenRef.current = null;
          localStorage.removeItem('access_token');
        }
      }

      if (cancelled) return;

      const refreshToken = localStorage.getItem('refresh_token');
      if (!refreshToken) {
        if (!cancelled) setLoading(false);
        return;
      }

      try {
        const { access_token, refresh_token: newRefresh } = await authApi.refresh(refreshToken);
        if (cancelled) return;
        accessTokenRef.current = access_token;
        localStorage.setItem('access_token', access_token);
        if (newRefresh) localStorage.setItem('refresh_token', newRefresh);
        const userData = await authApi.me(access_token);
        if (!cancelled) setUser(userData);
      } catch {
        if (!cancelled) {
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('access_token');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    restore();
    return () => { cancelled = true; };
  }, []);

  const login = useCallback(async ({ email, password }) => {
    const data = await authApi.login({ email, password });
    accessTokenRef.current = data.access_token;
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    const userData = await authApi.me(data.access_token);
    setUser(userData);
    return data.role;
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = localStorage.getItem('refresh_token');
    if (refreshToken) {
      try { await authApi.logout(refreshToken); } catch {}
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
