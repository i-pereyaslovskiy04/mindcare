/**
 * ThemeContext — палитра + режим (light/dark/system) → data-theme на <html>.
 *
 * Персистентность: localStorage (гости и MVP). Синхронизация с профилем
 * авторизованного пользователя (PATCH /api/auth/profile) — отдельный этап.
 * Режим 'system' следует prefers-color-scheme ОС и реагирует на её смену
 * без перезагрузки. Списки палитр/режимов продублированы в анти-FOUC
 * скрипте public/index.html — менять синхронно.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export const PALETTES = ['coffee', 'nature'];
export const MODES = ['light', 'dark', 'system'];

const STORAGE_PALETTE = 'app-theme-palette';
const STORAGE_MODE = 'app-theme-mode';

const DARK_MQ = '(prefers-color-scheme: dark)';

function readStored(key, allowed, fallback) {
  try {
    const value = window.localStorage.getItem(key);
    return allowed.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

function writeStored(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* приватный режим / отключённый storage — тема живёт до перезагрузки */
  }
}

function systemPrefersDark() {
  return typeof window.matchMedia === 'function' && window.matchMedia(DARK_MQ).matches;
}

export const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [palette, setPaletteState] = useState(() => readStored(STORAGE_PALETTE, PALETTES, 'coffee'));
  const [mode, setModeState] = useState(() => readStored(STORAGE_MODE, MODES, 'system'));
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  // Живая реакция на смену темы ОС (важно для режима «Системная»)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const mq = window.matchMedia(DARK_MQ);
    const onChange = (e) => setSystemDark(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const resolvedMode = mode === 'system' ? (systemDark ? 'dark' : 'light') : mode;
  const resolvedTheme = `${palette}-${resolvedMode}`;

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolvedTheme);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', resolvedMode === 'dark' ? '#1A1512' : '#4A3728');
    }
  }, [resolvedTheme, resolvedMode]);

  const setPalette = useCallback((next) => {
    if (!PALETTES.includes(next)) return;
    setPaletteState(next);
    writeStored(STORAGE_PALETTE, next);
  }, []);

  const setMode = useCallback((next) => {
    if (!MODES.includes(next)) return;
    setModeState(next);
    writeStored(STORAGE_MODE, next);
  }, []);

  const value = useMemo(
    () => ({ palette, setPalette, mode, setMode, resolvedTheme, resolvedMode }),
    [palette, setPalette, mode, setMode, resolvedTheme, resolvedMode]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return ctx;
}
