import { render, screen, fireEvent, within } from '@testing-library/react';
import EngagementsPage from './EngagementsPage';
import { useStudents } from '../../features/supervisor/hooks/useStudents';
import useUserContacts from '../../features/contacts/hooks/useUserContacts';

jest.mock('../../features/supervisor/hooks/useStudents');
jest.mock('../../features/contacts/hooks/useUserContacts');
jest.mock('../../features/supervisor/components/AssignModal', () => () => null);
jest.mock('../../features/tests/ui/StudentTestResults', () => () => null);
jest.mock('../../api/supervisor.api');

const STUDENTS = [
  { id: 1, uuid: 'uuid-1', full_name: 'Анна Первая', email: 'a@x.test', current_engagement: null },
  { id: 2, uuid: 'uuid-2', full_name: 'Борис Второй', email: 'b@x.test', current_engagement: null },
];

beforeEach(() => {
  useStudents.mockReturnValue({
    items: STUDENTS, loading: false, error: null, total: 2, page: 1,
    setPage: jest.fn(), query: '', setQuery: jest.fn(), refetch: jest.fn(),
  });
  useUserContacts.mockReturnValue({
    status: 'ready',
    data: { primary_phone: '+79001234567', items: [], catalog: null },
    error: null,
    refetch: jest.fn(),
  });
});

test('значения контактов в таблице не показываются, пока диалог не открыт', () => {
  render(<EngagementsPage />);
  expect(screen.getAllByRole('button', { name: /^Контакты:/ })).toHaveLength(2);
  expect(useUserContacts).not.toHaveBeenCalled();
  expect(screen.queryByText('+79001234567')).toBeNull();
});

test('«Контакты» открывает диалог выбранного студента и запрашивает его uuid', () => {
  render(<EngagementsPage />);
  fireEvent.click(screen.getByRole('button', { name: 'Контакты: Борис Второй' }));

  expect(useUserContacts).toHaveBeenCalledWith('uuid-2');
  expect(useUserContacts).not.toHaveBeenCalledWith('uuid-1');
  const dialog = screen.getByRole('dialog', { name: 'Контакты: Борис Второй' });
  expect(within(dialog).getByText('Основной телефон')).toBeInTheDocument();
  expect(within(dialog).getByText(/фиксируется в журнале/)).toBeInTheDocument();
});

test('закрытие диалога убирает контакты со страницы', () => {
  render(<EngagementsPage />);
  fireEvent.click(screen.getByRole('button', { name: 'Контакты: Анна Первая' }));
  fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));

  expect(screen.queryByRole('dialog', { name: 'Контакты: Анна Первая' })).toBeNull();
  expect(screen.queryByText('+79001234567')).toBeNull();
});

test('503 при фиксации в журнале — понятное сообщение, данных нет', () => {
  useUserContacts.mockReturnValue({ status: 'auditUnavailable', data: null, error: null, refetch: jest.fn() });
  render(<EngagementsPage />);
  fireEvent.click(screen.getByRole('button', { name: 'Контакты: Анна Первая' }));

  expect(screen.getByRole('alert')).toHaveTextContent('зафиксировать в журнале');
  expect(screen.queryByText('+79001234567')).toBeNull();
});
