import { render, screen, fireEvent } from '@testing-library/react';
import RoleChooser from './RoleChooser';
import * as AuthContext from './AuthContext';

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });
jest.mock('./AuthContext', () => ({ useAuth: jest.fn() }));

const setActiveRole = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  AuthContext.useAuth.mockReturnValue({
    user: { roles: ['admin', 'supervisor'] },
    setActiveRole,
  });
});

test('renders a real button per cabinet in priority order', () => {
  render(<RoleChooser roles={['admin', 'supervisor']} />);
  expect(screen.getByText('Выберите кабинет')).toBeInTheDocument();
  const buttons = screen.getAllByRole('button');
  expect(buttons.map((b) => b.textContent)).toEqual(['Администратор', 'Супервизор']);
});

test('choosing a cabinet sets activeRole and navigates', () => {
  render(<RoleChooser roles={['admin', 'supervisor']} />);
  fireEvent.click(screen.getByRole('button', { name: 'Супервизор' }));
  expect(setActiveRole).toHaveBeenCalledWith('supervisor');
  expect(mockNavigate).toHaveBeenCalledWith('/supervisor', { replace: true });
});
