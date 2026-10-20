import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useParams } from 'react-router-dom';
import { getStudentTestResults } from '../../api/tests.api';
import { useStudentCard } from '../../features/psychologist/hooks/useStudentCard';
import useUserContacts from '../../features/contacts/hooks/useUserContacts';
import PsychologistStudentCardPage from './PsychologistStudentCardPage';

jest.mock('../../features/psychologist/hooks/useStudentCard');
jest.mock('../../features/contacts/hooks/useUserContacts');
// StudentTestResults сам ходит в API: синтетический ответ, реальных запросов нет.
jest.mock('../../api/tests.api');
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...props }) => (
    <a
      href={to}
      onClick={(event) => {
        event.preventDefault();
        global.history.pushState({}, '', to);
      }}
      {...props}
    >
      {children}
    </a>
  ),
  useParams: jest.fn(),
}), { virtual: true });

function renderPage() {
  window.history.pushState({}, '', '/psychologist/students/7');
  return render(<PsychologistStudentCardPage />);
}

// Рендер с ожиданием асинхронного обновления StudentTestResults (список результатов),
// чтобы тест не завершался с невыполненными обновлениями состояния.
async function renderLoadedPage() {
  const view = renderPage();
  await screen.findByText('Пройденных тестов нет.');
  return view;
}

beforeEach(() => {
  getStudentTestResults.mockResolvedValue({ items: [] });
  useUserContacts.mockReturnValue({
    status: 'ready',
    data: { primary_phone: '+79001234567', items: [], catalog: null },
    error: null,
    refetch: jest.fn(),
  });
  useParams.mockReturnValue({ studentId: '7' });
  useStudentCard.mockReturnValue({
    student: {
      student_id: 7,
      student_uuid: 'student-uuid-7',
      full_name: 'Анна Смирнова',
      email: 'anna@example.test',
      assigned_at: '2026-01-10T10:00:00Z',
    },
    loading: false,
    error: null,
    refetch: jest.fn(),
  });
});

test('student detail card has active chat quick action', async () => {
  await renderLoadedPage();

  const chatLink = screen.getByRole('link', { name: /Чат со студентом/i });
  expect(chatLink).toHaveAttribute('href', '/psychologist/chat?student=7');
  expect(within(chatLink).queryByText('скоро')).not.toBeInTheDocument();
});

test('student detail chat action navigates to psychologist messenger query', async () => {
  await renderLoadedPage();

  userEvent.click(screen.getByRole('link', { name: /Чат со студентом/i }));

  expect(window.location.pathname).toBe('/psychologist/chat');
  expect(window.location.search).toBe('?student=7');
});

test('секция «Контакты» запрашивает контакты по uuid студента и показывает их', async () => {
  await renderLoadedPage();

  expect(useUserContacts).toHaveBeenCalledWith('student-uuid-7');
  expect(screen.getByRole('heading', { name: 'Контакты' })).toBeInTheDocument();
  expect(screen.getByText('Основной телефон')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: '+79001234567' })).toHaveAttribute('href', 'tel:+79001234567');
  expect(screen.getByText(/фиксируется в журнале/)).toBeInTheDocument();
});

test('контакты недоступны — нейтральный текст без данных', async () => {
  useUserContacts.mockReturnValue({ status: 'unavailable', data: null, error: null, refetch: jest.fn() });
  await renderLoadedPage();

  expect(screen.getByText('Контакты недоступны.')).toBeInTheDocument();
  expect(screen.queryByText('Основной телефон')).toBeNull();
});

test('контакты не запрашиваются, пока карточка не загружена', () => {
  useStudentCard.mockReturnValue({ student: null, loading: true, error: null, refetch: jest.fn() });
  renderPage();

  expect(useUserContacts).not.toHaveBeenCalled();
});

test('результаты психодиагностики запрашиваются по uuid студента и роли psychologist (через мок API)', async () => {
  await renderLoadedPage();

  expect(getStudentTestResults).toHaveBeenCalledTimes(1);
  expect(getStudentTestResults).toHaveBeenCalledWith('student-uuid-7', 'psychologist');
});

test('пока карточка не загружена, результаты тестов не запрашиваются', () => {
  useStudentCard.mockReturnValue({ student: null, loading: true, error: null, refetch: jest.fn() });
  renderPage();

  expect(getStudentTestResults).not.toHaveBeenCalled();
});
