import { render, screen } from '@testing-library/react';
import PsychologistMaterialsPage from './PsychologistMaterialsPage';
import { useAuth } from '../../../features/auth/AuthContext';

let mockHash = '';
jest.mock('react-router-dom', () => ({
  useLocation: () => ({ hash: mockHash }),
}), { virtual: true });
jest.mock('../../../features/auth/AuthContext', () => ({ useAuth: jest.fn() }));
// Содержимое вкладок проверяется в собственных тестах.
jest.mock('../../../features/materials/ui/MaterialsLibrary', () => () => <div>Библиотека материалов</div>);
jest.mock('../../../features/materials/ui/MyArticles', () => () => <div>Мои статьи</div>);

beforeEach(() => {
  mockHash = '';
  useAuth.mockReturnValue({ isImpersonating: false });
});

test('вкладки разделов — shared Tabs на всю ширину колонки (fill)', () => {
  render(<PsychologistMaterialsPage />);
  const list = screen.getByRole('tablist', { name: 'Разделы материалов' });
  expect(list.className).toMatch(/fill/);
  expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Библиотека', 'Мои материалы']);
  expect(screen.getByRole('tab', { name: 'Библиотека' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByRole('tabpanel', { name: 'Библиотека' })).toHaveTextContent('Библиотека материалов');
});

test('ссылка #my-materials открывает «Мои материалы»', () => {
  mockHash = '#my-materials';
  render(<PsychologistMaterialsPage />);
  expect(screen.getByRole('tab', { name: 'Мои материалы' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByText('Мои статьи')).toBeInTheDocument();
});

test('в режиме «под именем» вкладок нет', () => {
  useAuth.mockReturnValue({ isImpersonating: true });
  render(<PsychologistMaterialsPage />);
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.getByText('Библиотека материалов')).toBeInTheDocument();
});
