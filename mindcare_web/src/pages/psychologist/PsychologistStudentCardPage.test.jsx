import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useParams } from 'react-router-dom';
import { useStudentCard } from '../../features/psychologist/hooks/useStudentCard';
import PsychologistStudentCardPage from './PsychologistStudentCardPage';

jest.mock('../../features/psychologist/hooks/useStudentCard');
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

beforeEach(() => {
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

test('student detail card has active chat quick action', () => {
  renderPage();

  const chatLink = screen.getByRole('link', { name: /Чат со студентом/i });
  expect(chatLink).toHaveAttribute('href', '/psychologist/chat?student=7');
  expect(within(chatLink).queryByText('скоро')).not.toBeInTheDocument();
});

test('student detail chat action navigates to psychologist messenger query', () => {
  renderPage();

  userEvent.click(screen.getByRole('link', { name: /Чат со студентом/i }));

  expect(window.location.pathname).toBe('/psychologist/chat');
  expect(window.location.search).toBe('?student=7');
});
