/**
 * A11yContext — режим для слабовидящих (ГОСТ Р 52872-2019).
 *
 * Отдельный контекст, НЕ смешивается с ThemeContext: это самостоятельный
 * режим отображения со своей панелью настроек, а не ещё одна цветовая тема.
 * Настройки живут в localStorage и восстанавливаются при следующем визите.
 *
 * Применение — атрибуты на <html> (правила см. styles/tokens/a11y.css).
 * Изображения в режиме «скрыть» лишаются src на уровне DOM: браузер
 * рендерит alt-текст, CSS обводит его рамкой (CSS-only это не умеет —
 * img является replaced element).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

const STORAGE_KEY = 'app-a11y-settings';

export const SCHEMES = ['bw', 'wb', 'blue', 'beige'];
export const FONT_SCALES = [1, 1.5, 2];
export const SPACINGS = ['normal', 'medium', 'large'];
export const LEADINGS = ['1.5', '2'];
export const FONTS = ['sans', 'serif'];
export const IMAGES = ['show', 'hide', 'gray'];

export const DEFAULT_SETTINGS = {
  enabled: false,
  scheme: 'bw',
  fontScale: 1,
  spacing: 'normal',
  leading: '1.5',
  font: 'sans',
  images: 'show',
};

function sanitize(raw) {
  if (!raw || typeof raw !== 'object') return DEFAULT_SETTINGS;
  const scale = Number(raw.fontScale);
  return {
    enabled: Boolean(raw.enabled),
    scheme: SCHEMES.includes(raw.scheme) ? raw.scheme : DEFAULT_SETTINGS.scheme,
    fontScale: FONT_SCALES.includes(scale) ? scale : DEFAULT_SETTINGS.fontScale,
    spacing: SPACINGS.includes(raw.spacing) ? raw.spacing : DEFAULT_SETTINGS.spacing,
    leading: LEADINGS.includes(raw.leading) ? raw.leading : DEFAULT_SETTINGS.leading,
    font: FONTS.includes(raw.font) ? raw.font : DEFAULT_SETTINGS.font,
    images: IMAGES.includes(raw.images) ? raw.images : DEFAULT_SETTINGS.images,
  };
}

function readStored() {
  try {
    return sanitize(JSON.parse(window.localStorage.getItem(STORAGE_KEY)));
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function writeStored(settings) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    /* приватный режим — настройки живут до перезагрузки */
  }
}

/** Снимает/возвращает src у изображений: без src браузер рендерит alt. */
function applyImageHiding(hide) {
  document.querySelectorAll('img').forEach((img) => {
    if (hide) {
      if (img.getAttribute('src')) {
        img.dataset.a11ySrc = img.getAttribute('src');
        img.removeAttribute('src');
      }
    } else if (img.dataset.a11ySrc) {
      img.setAttribute('src', img.dataset.a11ySrc);
      delete img.dataset.a11ySrc;
    }
  });
}

const A11yContext = createContext(null);

export function A11yProvider({ children }) {
  const [settings, setSettings] = useState(readStored);

  // Атрибуты на <html> — их читают правила styles/tokens/a11y.css.
  useEffect(() => {
    const root = document.documentElement;
    if (!settings.enabled) {
      root.removeAttribute('data-a11y');
      root.removeAttribute('data-a11y-scheme');
      root.removeAttribute('data-a11y-spacing');
      root.removeAttribute('data-a11y-leading');
      root.removeAttribute('data-a11y-font');
      root.removeAttribute('data-a11y-images');
      root.style.removeProperty('--a11y-font-scale');
      return undefined;
    }
    root.setAttribute('data-a11y', 'on');
    root.setAttribute('data-a11y-scheme', settings.scheme);
    root.setAttribute('data-a11y-spacing', settings.spacing);
    root.setAttribute('data-a11y-leading', settings.leading);
    root.setAttribute('data-a11y-font', settings.font);
    root.setAttribute('data-a11y-images', settings.images);
    root.style.setProperty('--a11y-font-scale', String(settings.fontScale));
    return undefined;
  }, [settings]);

  // Скрытие изображений + слежение за новыми (SPA дорисовывает контент).
  useEffect(() => {
    const hide = settings.enabled && settings.images === 'hide';
    applyImageHiding(hide);
    if (!hide) return undefined;
    const observer = new MutationObserver(() => applyImageHiding(true));
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [settings.enabled, settings.images]);

  const update = useCallback((patch) => {
    setSettings((prev) => {
      const next = sanitize({ ...prev, ...patch });
      writeStored(next);
      return next;
    });
  }, []);

  const enable = useCallback(() => update({ enabled: true }), [update]);
  const disable = useCallback(() => update({ enabled: false }), [update]);

  const reset = useCallback(() => {
    // Сброс настроек оформления, но режим остаётся включённым.
    const next = { ...DEFAULT_SETTINGS, enabled: true };
    writeStored(next);
    setSettings(next);
  }, []);

  const value = useMemo(
    () => ({ settings, update, enable, disable, reset }),
    [settings, update, enable, disable, reset]
  );

  return <A11yContext.Provider value={value}>{children}</A11yContext.Provider>;
}

export function useA11y() {
  const ctx = useContext(A11yContext);
  if (!ctx) {
    throw new Error('useA11y must be used within A11yProvider');
  }
  return ctx;
}

export { A11yContext };
