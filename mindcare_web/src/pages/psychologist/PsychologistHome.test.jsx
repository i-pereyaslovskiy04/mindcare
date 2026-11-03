import { render, screen, within } from '@testing-library/react';
import PsychologistHome from './PsychologistHome';
import { usePsychologistCalendarRange } from '../../features/psychologist/hooks/usePsychologistCalendarRange';
import useClientsTotal from '../../features/psychologist/hooks/useClientsTotal';
import { useMessagesBadge } from '../../features/chat/hooks/useMessagesBadge';

jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });
jest.mock('../../features/psychologist/hooks/usePsychologistCalendarRange', () => ({
  usePsychologistCalendarRange: jest.fn(),
}));
jest.mock('../../features/psychologist/hooks/useClientsTotal', () => jest.fn());
jest.mock('../../features/chat/hooks/useMessagesBadge', () => ({ useMessagesBadge: jest.fn() }));

beforeEach(() => {
  jest.clearAllMocks();
  usePsychologistCalendarRange.mockReturnValue({ eventsByDay: {}, loading: false });
  useClientsTotal.mockReturnValue(4);
  useMessagesBadge.mockReturnValue(1);
});

test('нейтральное приветствие, без «в разработке» и «будут доступны позже»', () => {
  render(<PsychologistHome />);
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Здравствуйте!');
  expect(screen.queryByText(/в разработке|развивается|будут доступны позже|недоступны/i)).toBeNull();
  expect(screen.queryByText(/Сессий за месяц/)).toBeNull();
});

test('показатели с определённым смыслом', () => {
  render(<PsychologistHome />);
  expect(within(screen.getByRole('group', { name: 'Клиентов' })).getByText('4')).toBeInTheDocument();
  expect(within(screen.getByRole('group', { name: 'Встреч сегодня' })).getByText('0')).toBeInTheDocument();
  expect(within(screen.getByRole('group', { name: 'Диалогов с непрочитанным' })).getByText('1')).toBeInTheDocument();
  expect(useMessagesBadge).toHaveBeenCalledWith('psychologist');
});

test('неизвестное число клиентов — прочерк, а не ноль', () => {
  useClientsTotal.mockReturnValue(null);
  render(<PsychologistHome />);
  expect(within(screen.getByRole('group', { name: 'Клиентов' })).getByText('—')).toBeInTheDocument();
});

test('кнопки — рабочие ссылки', () => {
  render(<PsychologistHome />);
  expect(screen.getByRole('link', { name: 'Мои студенты' })).toHaveAttribute('href', '/psychologist/students');
  expect(screen.getByRole('link', { name: 'Настройки профиля' })).toHaveAttribute('href', '/psychologist/settings');
});
