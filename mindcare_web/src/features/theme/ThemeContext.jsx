/**
 * ThemeContext — палитра + режим (light/dark/system) → data-theme на <html>.
 *
 * Приоритет источников: явный выбор в текущей сессии > профиль пользователя >
 * localStorage > default (coffee / system).
 *
 * Для авторизованных тема хранится в профиле (PATCH /api/auth/profile,
 * soft-fail: сбой сети не ломает UI) и дублируется в localStorage — анти-FOUC
 * скрипт в public/index.html читает только его. Гости живут на localStorage.
 * Режим 'system' следует prefers-color-scheme ОС и реагирует на её смену
 * без перезагрузки. Списки палитр/режимов продублированы в анти-FOUC скрипте
 * и в backend-схеме ProfileUpdate — менять синхронно.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import * as authApi from '../../api/auth.api';

// 'hc' — высококонтрастный набор (AAA). Технически это тоже палитра:
// resolvedTheme = `${palette}-${resolvedMode}` → hc-light / hc-dark,
// поэтому режим (в т.ч. «Системная») работает и для контраста.
export const PALETTES = ['dongu', 'coffee', 'nature', 'classic', 'hc'];
export const MODES = ['light', 'dark', 'system'];

const STORAGE_PALETTE = 'app-theme-palette';
const STORAGE_MODE = 'app-theme-mode';
const SESSION_KEY = 'mindcare_session'; // тот же ключ, что в AuthContext

const DARK_MQ = '(prefers-color-scheme: dark)';
const CONTRAST_MQ = '(prefers-contrast: more)';

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

function hasSession() {
  try {
    return Boolean(window.localStorage.getItem(SESSION_KEY));
  } catch {
    return false;
  }
}

function systemPrefersDark() {
  return typeof window.matchMedia === 'function' && window.matchMedia(DARK_MQ).matches;
}

function systemPrefersContrast() {
  return typeof window.matchMedia === 'function' && window.matchMedia(CONTRAST_MQ).matches;
}

/** Палитра при первом визите: prefers-contrast: more → hc, иначе dongu (дефолт). */
function initialPalette() {
  const stored = readStored(STORAGE_PALETTE, PALETTES, null);
  if (stored) return stored;
  return systemPrefersContrast() ? 'hc' : 'dongu';
}

export const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [palette, setPaletteState] = useState(initialPalette);
  const [mode, setModeState] = useState(() => readStored(STORAGE_MODE, MODES, 'system'));
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  // Явный выбор в этой сессии имеет приоритет над темой из профиля
  // (пользователь мог переключить тему до того, как профиль подгрузился).
  const userChoseRef = useRef(false);

  // Живая реакция на смену темы ОС (важно для режима «Системная»)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const mq = window.matchMedia(DARK_MQ);
    const onChange = (e) => setSystemDark(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  // Подтягиваем тему из профиля авторизованного пользователя (переносимость
  // между устройствами). Гость и «не задано» в профиле → остаётся localStorage.
  useEffect(() => {
    if (!hasSession()) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const profile = await authApi.getProfile();
        if (cancelled || userChoseRef.current) return;
        if (PALETTES.includes(profile?.ui_theme_palette)) {
          setPaletteState(profile.ui_theme_palette);
          writeStored(STORAGE_PALETTE, profile.ui_theme_palette);
        }
        if (MODES.includes(profile?.ui_theme_mode)) {
          setModeState(profile.ui_theme_mode);
          writeStored(STORAGE_MODE, profile.ui_theme_mode);
        }
      } catch {
        /* soft-fail: тема остаётся из localStorage */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const resolvedMode = mode === 'system' ? (systemDark ? 'dark' : 'light') : mode;
  const resolvedTheme = `${palette}-${resolvedMode}`;

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolvedTheme);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', resolvedMode === 'dark' ? '#00152E' : '#2454A6');
    }
  }, [resolvedTheme, resolvedMode]);

  // Сохранение выбора в профиль — soft-fail: ошибка сети не ломает UI.
  const persistToProfile = useCallback((fields) => {
    if (!hasSession()) return;
    authApi.updateProfile(fields).catch(() => {});
  }, []);

  const setPalette = useCallback((next) => {
    if (!PALETTES.includes(next)) return;
    userChoseRef.current = true;
    setPaletteState(next);
    writeStored(STORAGE_PALETTE, next);
    persistToProfile({ ui_theme_palette: next });
  }, [persistToProfile]);

  const setMode = useCallback((next) => {
    if (!MODES.includes(next)) return;
    userChoseRef.current = true;
    setModeState(next);
    writeStored(STORAGE_MODE, next);
    persistToProfile({ ui_theme_mode: next });
  }, [persistToProfile]);

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
