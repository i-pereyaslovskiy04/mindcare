import { render, screen, within } from '@testing-library/react';
import SupervisorHome from './SupervisorHome';
import { useAuth } from '../../features/auth/AuthContext';
import usePendingVerificationsCount from '../../features/studentVerification/hooks/usePendingVerificationsCount';
import useReviewQueueCounts from '../../features/moderation/hooks/useReviewQueueCounts';

jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });
jest.mock('../../features/auth/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../features/studentVerification/hooks/usePendingVerificationsCount', () => jest.fn());
jest.mock('../../features/moderation/hooks/useReviewQueueCounts', () => jest.fn());

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({
    user: { id: 7, name: 'Иванова Анна Петровна', roles: ['supervisor'] },
    isImpersonating: false,
  });
  usePendingVerificationsCount.mockReturnValue(2);
  useReviewQueueCounts.mockReturnValue({ tests: 3, articles: 0 });
});

test('нейтральное приветствие без фамилии из ФИО', () => {
  render(<SupervisorHome />);
  const h1 = screen.getByRole('heading', { level: 1 });
  expect(h1).toHaveTextContent('Здравствуйте!');
  expect(h1).not.toHaveTextContent('Иванова');
});

test('нет ложных обещаний и выдуманных показателей', () => {
  render(<SupervisorHome />);
  expect(screen.queryByText(/в разработке|будут доступны позже|скоро/i)).toBeNull();
  expect(screen.queryByText(/Сессий на проверке|Отчёт/i)).toBeNull();
  expect(screen.queryByText(/^Психологов$/)).toBeNull();
});

test('показатели — реальные очереди проверки', () => {
  render(<SupervisorHome />);
  expect(within(screen.getByRole('group', { name: 'Тесты на проверке' })).getByText('3')).toBeInTheDocument();
  expect(within(screen.getByRole('group', { name: 'Материалы на проверке' })).getByText('0')).toBeInTheDocument();
  expect(within(screen.getByRole('group', { name: 'Заявки на подтверждение' })).getByText('2')).toBeInTheDocument();
  expect(useReviewQueueCounts).toHaveBeenCalledWith(true, 7);
  expect(usePendingVerificationsCount).toHaveBeenCalledWith(true, 7);
});

test('при входе под именем очереди не запрашиваются, значения — прочерк', () => {
  useAuth.mockReturnValue({ user: { id: 7, roles: ['supervisor'] }, isImpersonating: true });
  usePendingVerificationsCount.mockReturnValue(null);
  useReviewQueueCounts.mockReturnValue({ tests: null, articles: null });
  render(<SupervisorHome />);
  expect(useReviewQueueCounts).toHaveBeenCalledWith(false, 7);
  expect(within(screen.getByRole('group', { name: 'Тесты на проверке' })).getByText('—')).toBeInTheDocument();
});

test('«Настройки профиля» — ссылка на настройки; быстрые ссылки ведут в рабочие разделы', () => {
  render(<SupervisorHome />);
  expect(screen.getByRole('link', { name: 'Настройки профиля' })).toHaveAttribute('href', '/supervisor/settings');
  expect(screen.getByRole('link', { name: /Тесты/ })).toHaveAttribute('href', '/supervisor/tests');
  expect(screen.getByRole('link', { name: /Подтверждение студентов/ }))
    .toHaveAttribute('href', '/supervisor/student-verifications');
});
