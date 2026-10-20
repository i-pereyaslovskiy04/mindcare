import { render, screen } from '@testing-library/react';
import Navbar from './Navbar';
import * as AuthContext from '../../features/auth/AuthContext';

jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });
jest.mock('../../features/auth/AuthContext', () => ({ useAuth: jest.fn() }));

test('authenticated cabinet link points to /dashboard (chooser decides cabinet)', () => {
  AuthContext.useAuth.mockReturnValue({ isAuthenticated: true, loading: false });
  render(<Navbar onOpenAuth={jest.fn()} />);
  const link = screen.getByLabelText('Личный кабинет');
  expect(link).toHaveAttribute('href', '/dashboard');
});
