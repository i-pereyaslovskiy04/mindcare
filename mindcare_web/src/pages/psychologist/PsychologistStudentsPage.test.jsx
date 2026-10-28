import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useMyStudents } from '../../features/psychologist/hooks/useMyStudents';
import PsychologistStudentsPage from './PsychologistStudentsPage';
import { createClientAssignment, getClientAssignments } from '../../api/assignments.api';

jest.mock('../../features/psychologist/hooks/useMyStudents');
jest.mock('../../api/assignments.api');
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
}), { virtual: true });

function renderPage() {
  window.history.pushState({}, '', '/psychologist/students');
  return render(<PsychologistStudentsPage />);
}

beforeEach(() => {
  useMyStudents.mockReturnValue({
    items: [
      {
        engagement_id: 11,
        student_id: 7,
        student_uuid: 'student-uuid-7',
        full_name: 'Анна Смирнова',
        email: 'anna@example.test',
        assigned_at: '2026-01-10T10:00:00Z',
      },
    ],
    loading: false,
    error: null,
    total: 1,
    page: 1,
    setPage: jest.fn(),
    query: '',
    setQuery: jest.fn(),
    refetch: jest.fn(),
  });
});

test('student list card has active chat action', () => {
  renderPage();

  const chatLink = screen.getByRole('link', { name: /Чат со студентом/i });
  expect(chatLink).toHaveAttribute('href', '/psychologist/chat?student=7');
  expect(chatLink).not.toHaveAttribute('disabled');
  expect(within(chatLink).queryByText('скоро')).not.toBeInTheDocument();
});

test('student list chat action navigates to psychologist messenger query', () => {
  renderPage();

  userEvent.click(screen.getByRole('link', { name: /Чат со студентом/i }));

  expect(window.location.pathname).toBe('/psychologist/chat');
  expect(window.location.search).toBe('?student=7');
});

test('быстрое действие «Выдать задание» в списке: без перехода в карточку и без чтения заданий', async () => {
  createClientAssignment.mockResolvedValue({ uuid: 'a-1', status: 'active', changed: true });
  renderPage();

  userEvent.click(screen.getByRole('button', { name: 'Выдать задание: Анна Смирнова' }));
  const dialog = screen.getByRole('dialog', { name: 'Задание: Анна Смирнова' });
  expect(window.location.pathname).toBe('/psychologist/students');

  userEvent.type(within(dialog).getByLabelText('Текст задания'), 'Дневник сна на неделю');
  userEvent.click(within(dialog).getByRole('button', { name: 'Выдать задание' }));

  expect(createClientAssignment).toHaveBeenCalledWith('student-uuid-7', {
    text: 'Дневник сна на неделю', dueDate: '', articleUuid: undefined,
  });
  expect(await screen.findByText('Задание выдано: Анна Смирнова.')).toHaveAttribute('role', 'status');
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Задание: Анна Смирнова' })).toBeNull());
  expect(getClientAssignments).not.toHaveBeenCalled();
});

test('ошибка выдачи — диалог остаётся открытым с сообщением', async () => {
  createClientAssignment.mockRejectedValue(Object.assign(new Error('x'), { status: 404 }));
  renderPage();
  userEvent.click(screen.getByRole('button', { name: 'Выдать задание: Анна Смирнова' }));
  const dialog = screen.getByRole('dialog', { name: 'Задание: Анна Смирнова' });
  userEvent.type(within(dialog).getByLabelText('Текст задания'), 'Задание');
  userEvent.click(within(dialog).getByRole('button', { name: 'Выдать задание' }));
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Сопровождение недоступно');
  expect(screen.getByRole('dialog', { name: 'Задание: Анна Смирнова' })).toBeInTheDocument();
});

