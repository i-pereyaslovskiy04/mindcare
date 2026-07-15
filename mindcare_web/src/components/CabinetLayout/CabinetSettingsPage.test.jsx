import { render, screen } from '@testing-library/react';
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
