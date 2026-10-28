import { fireEvent, render, screen } from '@testing-library/react';
import CabinetSettingsPage from './CabinetSettingsPage';

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
}), { virtual: true });
jest.mock('../../features/auth/AuthContext', () => ({
  useAuth: () => ({ user: { name: 'Тест Тестов', email: 't@t.t' }, logout: jest.fn() }),
}));

test('shows the route cabinet role label, not legacy user.role (psychologist)', () => {
  render(<CabinetSettingsPage cabinetRole="psychologist" />);
  expect(screen.getByText('Психолог')).toBeInTheDocument();
});

test('shows the supervisor label for the supervisor route', () => {
  render(<CabinetSettingsPage cabinetRole="supervisor" />);
  expect(screen.getByText('Супервизор')).toBeInTheDocument();
});

// ── Разделы — shared Tabs (тот же паттерн, что в настройках студента) ──────

describe.each(['psychologist', 'supervisor'])('настройки кабинета %s: вкладки', (role) => {
  const panel = (name) => screen.getByRole('tabpanel', { name });

  test('три раздела, по умолчанию «Профиль»; связи tab ↔ tabpanel', () => {
    render(<CabinetSettingsPage cabinetRole={role} />);
    const list = screen.getByRole('tablist', { name: 'Разделы настроек' });
    expect(list.className).toMatch(/fill/);
    expect(screen.getAllByRole('tab').map((t) => t.textContent))
      .toEqual(['Профиль', 'Уведомления', 'Безопасность']);
    const profileTab = screen.getByRole('tab', { name: 'Профиль' });
    expect(profileTab).toHaveAttribute('aria-selected', 'true');
    expect(profileTab).toHaveAttribute('aria-controls', panel('Профиль').id);
    expect(screen.queryByRole('tabpanel', { name: 'Безопасность' })).toBeNull();   // скрыта
  });

  test('переключение показывает нужный раздел; содержимое разделов прежнее', () => {
    render(<CabinetSettingsPage cabinetRole={role} />);
    expect(screen.getByRole('heading', { name: 'Профиль' })).toBeVisible();

    fireEvent.click(screen.getByRole('tab', { name: 'Уведомления' }));
    expect(screen.getByRole('tab', { name: 'Уведомления' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('heading', { name: 'Уведомления' })).toBeVisible();
    expect(screen.getByText('Напоминания о сессиях')).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Профиль' })).toBeNull();   // панель скрыта

    fireEvent.click(screen.getByRole('tab', { name: 'Безопасность' }));
    expect(screen.getByRole('heading', { name: 'Безопасность' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Изменить пароль' })).toBeVisible();
  });

  test('все разделы смонтированы: черновик пароля переживает смену вкладки', () => {
    render(<CabinetSettingsPage cabinetRole={role} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Безопасность' }));
    // Подписи этой формы не связаны с полями (прежний код) — поле по autocomplete.
    // eslint-disable-next-line testing-library/no-node-access
    const current = () => document.querySelector('input[autocomplete="current-password"]');
    fireEvent.change(current(), { target: { value: 'draft-pass' } });
    fireEvent.click(screen.getByRole('tab', { name: 'Профиль' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Безопасность' }));
    expect(current()).toHaveValue('draft-pass');
  });
});
