import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import LoginForm from './LoginForm';
import * as AuthContext from '../AuthContext';

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });
jest.mock('../AuthContext', () => ({ useAuth: jest.fn() }));

const login = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  login.mockResolvedValue({ roles: ['psychologist', 'supervisor'] });
  AuthContext.useAuth.mockReturnValue({ login });
});

test('successful login navigates to /dashboard (not a role-specific home)', async () => {
  render(<LoginForm onSuccess={jest.fn()} onForgotPassword={jest.fn()} />);

  fireEvent.change(screen.getByLabelText('Email'), {
    target: { value: 'user@donnu.ru' },
  });
  fireEvent.change(screen.getByLabelText('Пароль'), {
    target: { value: 'secret123' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Войти' }));

  await waitFor(() => expect(login).toHaveBeenCalled());
  expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
});
