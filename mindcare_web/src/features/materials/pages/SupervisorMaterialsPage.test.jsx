import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SupervisorMaterialsPage from './SupervisorMaterialsPage';
import { useAuth } from '../../auth/AuthContext';

jest.mock('../../auth/AuthContext', () => ({ useAuth: jest.fn() }));
// Содержимое вкладок проверяется в собственных тестах.
jest.mock('../ui/ArticleReview', () => () => <div>Очередь модерации</div>);
jest.mock('../ui/MyArticles', () => (props) => <div>Мои материалы: {props.role}</div>);

beforeEach(() => jest.clearAllMocks());

test('вкладки «На проверке» и «Мои материалы» (публикует сам)', () => {
  useAuth.mockReturnValue({ isImpersonating: false });
  render(<SupervisorMaterialsPage />);
  expect(screen.getByRole('heading', { name: 'Материалы' })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'На проверке' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByText('Очередь модерации')).toBeInTheDocument();

  userEvent.click(screen.getByRole('tab', { name: 'Мои материалы' }));
  expect(screen.getByText('Мои материалы: supervisor')).toBeInTheDocument();
  expect(screen.queryByText('Очередь модерации')).toBeNull();
});

test('в режиме «под именем» — пояснение без вкладок и запросов', () => {
  useAuth.mockReturnValue({ isImpersonating: true });
  render(<SupervisorMaterialsPage />);
  expect(screen.getByText('Материалы недоступны при входе под именем пользователя.')).toBeInTheDocument();
  expect(screen.queryByRole('tab')).toBeNull();
  expect(screen.queryByText('Очередь модерации')).toBeNull();
});
