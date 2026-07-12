/**
 * Синхронизация темы с профилем пользователя (T3).
 * Приоритет источников: явный выбор в сессии > профиль > localStorage > default.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ThemeProvider } from './ThemeContext';
import ThemeToggle from './ThemeToggle';
import * as authApi from '../../api/auth.api';

jest.mock('../../api/auth.api');

const SESSION_KEY = 'mindcare_session';

function renderThemed() {
  return render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>
  );
}

describe('ThemeProvider ↔ профиль пользователя', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    authApi.updateProfile.mockResolvedValue({});
  });

  afterEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  test('гость: профиль не запрашивается, тема из localStorage', async () => {
    localStorage.setItem('app-theme-mode', 'dark');
    renderThemed();
    expect(authApi.getProfile).not.toHaveBeenCalled();
    expect(document.documentElement.getAttribute('data-theme')).toBe('coffee-dark');
  });

  test('авторизованный: тема из профиля применяется и пишется в localStorage', async () => {
    localStorage.setItem(SESSION_KEY, 'tok');
    authApi.getProfile.mockResolvedValue({
      ui_theme_palette: 'classic',
      ui_theme_mode: 'dark',
    });
    renderThemed();
    await waitFor(() =>
      expect(document.documentElement.getAttribute('data-theme')).toBe('classic-dark')
    );
    // Анти-FOUC скрипт читает только localStorage — дублируем туда.
    expect(localStorage.getItem('app-theme-palette')).toBe('classic');
    expect(localStorage.getItem('app-theme-mode')).toBe('dark');
  });

  test('профиль без темы (null) не перетирает localStorage', async () => {
    localStorage.setItem(SESSION_KEY, 'tok');
    localStorage.setItem('app-theme-mode', 'dark');
    authApi.getProfile.mockResolvedValue({
      ui_theme_palette: null,
      ui_theme_mode: null,
    });
    renderThemed();
    await waitFor(() => expect(authApi.getProfile).toHaveBeenCalled());
    expect(document.documentElement.getAttribute('data-theme')).toBe('coffee-dark');
  });

  test('сбой запроса профиля не ломает тему (soft-fail)', async () => {
    localStorage.setItem(SESSION_KEY, 'tok');
    localStorage.setItem('app-theme-palette', 'nature');
    authApi.getProfile.mockRejectedValue(new Error('network'));
    renderThemed();
    await waitFor(() => expect(authApi.getProfile).toHaveBeenCalled());
    expect(document.documentElement.getAttribute('data-theme')).toBe('nature-light');
  });

  test('выбор пользователя шлётся в профиль (PATCH только изменённого поля)', async () => {
    localStorage.setItem(SESSION_KEY, 'tok');
    authApi.getProfile.mockResolvedValue({ ui_theme_palette: null, ui_theme_mode: null });
    renderThemed();

    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
    await waitFor(() =>
      expect(authApi.updateProfile).toHaveBeenCalledWith({ ui_theme_mode: 'dark' })
    );

    fireEvent.click(screen.getByRole('button', { name: 'Кофейная палитра' }));
    await waitFor(() =>
      expect(authApi.updateProfile).toHaveBeenCalledWith({ ui_theme_palette: 'coffee' })
    );
  });

  test('сбой PATCH не ломает UI (soft-fail)', async () => {
    localStorage.setItem(SESSION_KEY, 'tok');
    authApi.getProfile.mockResolvedValue({ ui_theme_palette: null, ui_theme_mode: null });
    authApi.updateProfile.mockRejectedValue(new Error('network'));
    renderThemed();

    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
    await waitFor(() => expect(authApi.updateProfile).toHaveBeenCalled());
    expect(document.documentElement.getAttribute('data-theme')).toBe('coffee-dark');
  });

  test('явный выбор в сессии имеет приоритет над темой из профиля', async () => {
    localStorage.setItem(SESSION_KEY, 'tok');
    let resolveProfile;
    authApi.getProfile.mockReturnValue(
      new Promise((resolve) => { resolveProfile = resolve; })
    );
    renderThemed();

    // Пользователь переключил тему до того, как профиль ответил.
    fireEvent.click(screen.getByRole('button', { name: 'Светлая тема' }));
    resolveProfile({ ui_theme_palette: 'nature', ui_theme_mode: 'dark' });

    await waitFor(() => expect(authApi.getProfile).toHaveBeenCalled());
    expect(document.documentElement.getAttribute('data-theme')).toBe('coffee-light');
  });

  test('гость: выбор темы не шлёт PATCH', async () => {
    renderThemed();
    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
    expect(authApi.updateProfile).not.toHaveBeenCalled();
  });
});
