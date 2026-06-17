import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useMyStudents } from '../../features/psychologist/hooks/useMyStudents';
import PsychologistStudentsPage from './PsychologistStudentsPage';

jest.mock('../../features/psychologist/hooks/useMyStudents');
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
