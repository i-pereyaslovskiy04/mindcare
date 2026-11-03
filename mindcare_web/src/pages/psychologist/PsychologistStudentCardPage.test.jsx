import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useParams } from 'react-router-dom';
import { getStudentTestResults } from '../../api/tests.api';
import { getClientAssignments } from '../../api/assignments.api';
import { getClientAppointments } from '../../api/appointments.api';
import { createClientNote, getClientNotes } from '../../api/sessionNotes.api';
import { useStudentCard } from '../../features/psychologist/hooks/useStudentCard';
import useUserContacts from '../../features/contacts/hooks/useUserContacts';
import PsychologistStudentCardPage from './PsychologistStudentCardPage';

jest.mock('../../features/psychologist/hooks/useStudentCard');
jest.mock('../../features/contacts/hooks/useUserContacts');
// StudentTestResults сам ходит в API: синтетический ответ, реальных запросов нет.
jest.mock('../../api/tests.api');
// Раздел «Задания» сам ходит в API: синтетический пустой ответ.
jest.mock('../../api/assignments.api');
// Раздел «Встречи с клиентом» сам ходит в API: синтетический пустой ответ.
jest.mock('../../api/appointments.api');
// Раздел «Заметки» сам ходит в API: синтетический пустой ответ.
jest.mock('../../api/sessionNotes.api');
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
  await screen.findByText('Заданий пока нет.');
  await screen.findByText('Прошедших встреч пока нет.');
  await screen.findByText('Заметок пока нет.');
  return view;
}

beforeEach(() => {
  getStudentTestResults.mockResolvedValue({ items: [] });
  getClientAssignments.mockResolvedValue({ items: [], has_more: false, next_cursor: null, total: 0 });
  getClientAppointments.mockResolvedValue({ items: [], has_more: false, next_cursor: null });
  getClientNotes.mockResolvedValue({ items: [], has_more: false, next_cursor: null });
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
  expect(screen.getByText('Просмотр контактов фиксируется в журнале.')).toBeInTheDocument();
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
  expect(getStudentTestResults).toHaveBeenCalledWith(
    'student-uuid-7', 'psychologist', { page: 1, size: 20 },
  );
});

test('заглушки «Назначение тестов» и обещания этой функции нет', async () => {
  await renderLoadedPage();

  expect(screen.queryByText('Назначение тестов')).toBeNull();
  expect(screen.queryByText(/назначени[ея] тест/i)).toBeNull();
});

test('пока карточка не загружена, результаты тестов не запрашиваются', () => {
  useStudentCard.mockReturnValue({ student: null, loading: true, error: null, refetch: jest.fn() });
  renderPage();

  expect(getStudentTestResults).not.toHaveBeenCalled();
});

test('секция «Задания» запрашивает задания по uuid студента; заглушки назначения материалов нет', async () => {
  await renderLoadedPage();

  expect(screen.getByRole('heading', { name: 'Задания' })).toBeInTheDocument();
  expect(getClientAssignments).toHaveBeenCalledWith('student-uuid-7', expect.objectContaining({ before: undefined }));
  expect(screen.getByRole('button', { name: 'Выбрать из библиотеки' })).toBeInTheDocument();
  expect(screen.queryByText('Материалы и тесты')).toBeNull();
});

test('пока карточка не загружена, задания не запрашиваются', () => {
  useStudentCard.mockReturnValue({ student: null, loading: true, error: null, refetch: jest.fn() });
  renderPage();

  expect(getClientAssignments).not.toHaveBeenCalled();
});

test('«Встречи с клиентом»: активное быстрое действие и раздел по uuid клиента', async () => {
  await renderLoadedPage();

  const action = screen.getByRole('button', { name: /Встречи с клиентом/ });
  expect(action).toBeEnabled();
  expect(within(action).queryByText('скоро')).toBeNull();
  expect(screen.queryByText('Расписание')).toBeNull();
  const heading = screen.getByRole('heading', { name: 'Встречи с клиентом' });
  expect(getClientAppointments).toHaveBeenCalledWith(
    'student-uuid-7', expect.objectContaining({ view: 'upcoming' }),
  );
  expect(getClientAppointments).toHaveBeenCalledWith(
    'student-uuid-7', expect.objectContaining({ view: 'history' }),
  );
  userEvent.click(action);
  expect(heading).toHaveFocus();
});

test('переход по #client-meetings переводит фокус на раздел встреч', async () => {
  window.history.pushState({}, '', '/psychologist/students/7#client-meetings');
  render(<PsychologistStudentCardPage />);
  await screen.findByText('Прошедших встреч пока нет.');
  await screen.findByText('Заметок пока нет.');
  expect(screen.getByRole('heading', { name: 'Встречи с клиентом' })).toHaveFocus();
});

test('пока карточка не загружена, встречи не запрашиваются', () => {
  useStudentCard.mockReturnValue({ student: null, loading: true, error: null, refetch: jest.fn() });
  renderPage();

  expect(getClientAppointments).not.toHaveBeenCalled();
});

test('«Заметки»: активное действие, раздел по uuid клиента, будущего — только супервизия', async () => {
  await renderLoadedPage();

  const action = screen.getByRole('button', { name: /^Заметки$/ });
  expect(within(action).queryByText('скоро')).toBeNull();
  expect(getClientNotes).toHaveBeenCalledWith('student-uuid-7', expect.objectContaining({ before: undefined }));
  userEvent.click(action);
  expect(screen.getByRole('heading', { name: 'Заметки' })).toHaveFocus();
  expect(screen.queryByText('Рабочие заметки психолога')).toBeNull();
  expect(screen.queryByText('История консультаций и сессий')).toBeNull();
  expect(screen.getByText('Запрос супервизии')).toBeInTheDocument();
  expect(screen.queryByText('скоро')).toBeNull();
});

test('«Заметка» у встречи открывает форму с привязкой к этой встрече', async () => {
  getClientAppointments.mockImplementation((uuid, { view }) => Promise.resolve(view === 'history'
    ? {
      items: [{
        uuid: 'appt-1', starts_at: '2026-10-20T10:00:00+03:00', ends_at: '2026-10-20T10:50:00+03:00',
        status: 'completed', meeting_type_name: null, modality: 'online', via_card: false,
        can_mark_outcome: false,
      }],
      has_more: false, next_cursor: null,
    }
    : { items: [], has_more: false, next_cursor: null }));
  createClientNote.mockResolvedValueOnce({});
  renderPage();
  await screen.findByText('Заметок пока нет.');
  userEvent.click(await screen.findByRole('button', { name: 'Заметка' }));

  expect(screen.getByText('К встрече: 20 октября 2026 г., 10:00–10:50')).toBeInTheDocument();
  userEvent.type(screen.getByLabelText('Новая заметка'), 'Итоги');
  userEvent.click(screen.getByRole('button', { name: 'Сохранить заметку' }));
  await screen.findByText('Заметок пока нет.');
  expect(createClientNote).toHaveBeenCalledWith('student-uuid-7', {
    content: 'Итоги', noteType: 'general', appointmentUuid: 'appt-1',
  });
});

// ── Смена клиента в карточке: key-ремонт ClientNotes, как в реальной странице ──

function studentOf(id) {
  return {
    student: {
      student_id: id,
      student_uuid: `student-uuid-${id}`,
      full_name: `Клиент ${id}`,
      email: `c${id}@example.test`,
      assigned_at: '2026-01-10T10:00:00Z',
    },
    loading: false,
    error: null,
    refetch: jest.fn(),
  };
}

const HISTORY_MEETINGS = {
  'student-uuid-7': {
    uuid: 'appt-A', starts_at: '2026-10-20T10:00:00+03:00', ends_at: '2026-10-20T10:50:00+03:00',
  },
  'student-uuid-8': {
    uuid: 'appt-B', starts_at: '2026-10-21T12:00:00+03:00', ends_at: '2026-10-21T12:50:00+03:00',
  },
};

function mockMeetingsPerClient() {
  getClientAppointments.mockImplementation((uuid, { view }) => {
    const m = HISTORY_MEETINGS[uuid];
    return Promise.resolve(view === 'history' && m
      ? {
        items: [{
          ...m, status: 'completed', meeting_type_name: null, modality: 'online',
          via_card: false, can_mark_outcome: false,
        }],
        has_more: false, next_cursor: null,
      }
      : { items: [], has_more: false, next_cursor: null });
  });
}

function switchClient(view, id) {
  useParams.mockReturnValue({ studentId: String(id) });
  useStudentCard.mockReturnValue(studentOf(id));
  view.rerender(<PageForTest />);
}

function PageForTest() {
  return <PsychologistStudentCardPage />;
}

async function pickMeetingNote() {
  userEvent.click(await screen.findByRole('button', { name: 'Заметка' }));
}

const WHEN_B = 'К встрече: 21 октября 2026 г., 12:00–12:50';

describe('смена клиента при незавершённом создании заметки', () => {
  beforeEach(() => {
    mockMeetingsPerClient();
  });

  async function startCreateAtA() {
    let settle;
    const pending = new Promise((resolve, reject) => { settle = { resolve, reject }; });
    createClientNote.mockReturnValueOnce(pending);
    window.history.pushState({}, '', '/psychologist/students/7');
    const view = render(<PageForTest />);
    await screen.findByText('Заметок пока нет.');
    await pickMeetingNote();
    userEvent.type(screen.getByLabelText('Новая заметка'), 'Для клиента A');
    userEvent.click(screen.getByRole('button', { name: 'Сохранить заметку' }));
    await waitFor(() => expect(createClientNote).toHaveBeenCalledWith('student-uuid-7', {
      content: 'Для клиента A', noteType: 'general', appointmentUuid: 'appt-A',
    }));
    return { view, settle };
  }

  test('A → B: успех запроса A не снимает привязку встречи B и не трогает форму', async () => {
    const { view, settle } = await startCreateAtA();
    switchClient(view, 8);
    await screen.findByText('Заметок пока нет.');
    await pickMeetingNote();
    expect(await screen.findByText(WHEN_B)).toBeInTheDocument();
    userEvent.type(screen.getByLabelText('Новая заметка'), 'Для клиента B');
    const callsBefore = getClientNotes.mock.calls.length;

    await act(async () => { settle.resolve({}); });

    expect(screen.getByText(WHEN_B)).toBeInTheDocument();
    expect(screen.getByLabelText('Новая заметка')).toHaveValue('Для клиента B');
    expect(screen.getByRole('button', { name: 'Сохранить заметку' })).toBeEnabled();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(getClientNotes.mock.calls.length).toBe(callsBefore);   // список B не перечитан
  });

  test('A → B: ошибка запроса A не показывает сообщение и не блокирует форму B', async () => {
    const { view, settle } = await startCreateAtA();
    switchClient(view, 8);
    await screen.findByText('Заметок пока нет.');
    await pickMeetingNote();
    userEvent.type(screen.getByLabelText('Новая заметка'), 'Для клиента B');

    await act(async () => { settle.reject(Object.assign(new Error('x'), { status: 503 })); });

    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByText(WHEN_B)).toBeInTheDocument();
    expect(screen.getByLabelText('Новая заметка')).toHaveValue('Для клиента B');
    expect(screen.getByRole('button', { name: 'Сохранить заметку' })).toBeEnabled();
  });

  test('A → B → A: ответ старого запроса A не влияет на новую карточку A', async () => {
    const { view, settle } = await startCreateAtA();
    switchClient(view, 8);
    await screen.findByText('Заметок пока нет.');
    switchClient(view, 7);
    await screen.findByText('Заметок пока нет.');
    userEvent.type(screen.getByLabelText('Новая заметка'), 'Новый черновик A');
    const callsBefore = getClientNotes.mock.calls.length;

    await act(async () => { settle.resolve({}); });

    expect(screen.getByLabelText('Новая заметка')).toHaveValue('Новый черновик A');
    expect(screen.getByRole('button', { name: 'Сохранить заметку' })).toBeEnabled();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(getClientNotes.mock.calls.length).toBe(callsBefore);
    // новая карточка A независимо отправляет свою заметку
    createClientNote.mockResolvedValueOnce({});
    userEvent.click(screen.getByRole('button', { name: 'Сохранить заметку' }));
    await waitFor(() => expect(createClientNote).toHaveBeenLastCalledWith('student-uuid-7', {
      content: 'Новый черновик A', noteType: 'general', appointmentUuid: null,   // привязка прежней сессии A сброшена
    }));
  });
});
