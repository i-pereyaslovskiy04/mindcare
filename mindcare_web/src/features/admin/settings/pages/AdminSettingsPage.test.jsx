import { render, screen } from '@testing-library/react';
import AdminSettingsPage from './AdminSettingsPage';

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
}), { virtual: true });

jest.mock('../../../auth/AuthContext', () => ({
  useAuth: () => ({ logout: jest.fn() }),
}));

test('renders only the password-change card, no email-domains section', () => {
  render(<AdminSettingsPage />);
  expect(screen.getByRole('heading', { name: 'Безопасность', level: 1 })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Смена пароля', level: 2 })).toBeInTheDocument();
  expect(screen.queryByText('Разрешённые почтовые домены')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Сменить пароль' })).toBeInTheDocument();
});
