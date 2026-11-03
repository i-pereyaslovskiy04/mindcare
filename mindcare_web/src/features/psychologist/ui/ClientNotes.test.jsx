import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ClientNotes from './ClientNotes';
import { createClientNote, getClientNotes, updateClientNote } from '../../../api/sessionNotes.api';

jest.mock('../../../api/sessionNotes.api');

const apiError = (status) => Object.assign(new Error('x'), { status });
const note = (uuid, extra = {}) => ({
  uuid, note_type: 'general', content: `Текст ${uuid}`, version: 1,
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z', appointment: null, ...extra,
});
const page = (items) => ({ items, has_more: false, next_cursor: null });
const MEETING = { uuid: 'appt-page2', starts_at: '2026-09-01T10:00:00+03:00', ends_at: '2026-09-01T10:50:00+03:00' };

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  jest.resetAllMocks();
  getClientNotes.mockResolvedValue(page([note('n1')]));
});

test('заметка к встрече: привязка показана и уходит в запрос; после сохранения снимается', async () => {
  const onClear = jest.fn();
  createClientNote.mockResolvedValueOnce(note('n2'));
  render(
    <ClientNotes studentUuid="c-1" linkedMeeting={{ clientUuid: 'c-1', meeting: MEETING }}
      onClearLinkedMeeting={onClear} />,
  );
  expect(await screen.findByText('К встрече: 1 сентября 2026 г., 10:00–10:50')).toBeInTheDocument();
  const textarea = screen.getByLabelText('Новая заметка');
  expect(textarea).toHaveFocus();
  userEvent.type(textarea, 'План на встречу');
  userEvent.click(screen.getByRole('button', { name: 'Сохранить заметку' }));
  await waitFor(() => expect(createClientNote).toHaveBeenCalledWith('c-1', {
    content: 'План на встречу', noteType: 'general', appointmentUuid: 'appt-page2',
  }));
  await waitFor(() => expect(onClear).toHaveBeenCalled());
  expect(textarea).toHaveValue('');
});

test('встреча другого клиента не применяется', async () => {
  render(<ClientNotes studentUuid="c-2" linkedMeeting={{ clientUuid: 'c-1', meeting: MEETING }} />);
  await screen.findByText('Текст n1');
  expect(screen.queryByText(/К встрече:/)).toBeNull();
});

test('ошибка создания: введённый текст не теряется', async () => {
  createClientNote.mockRejectedValueOnce(apiError(500));
  render(<ClientNotes studentUuid="c-1" />);
  await screen.findByText('Текст n1');
  userEvent.type(screen.getByLabelText('Новая заметка'), 'Важный текст');
  userEvent.click(screen.getByRole('button', { name: 'Сохранить заметку' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/Введённый текст сохранён/);
  expect(screen.getByLabelText('Новая заметка')).toHaveValue('Важный текст');
});

function paged(p2 = note('p2')) {
  getClientNotes.mockImplementation((uuid, { before }) => Promise.resolve(before
    ? { items: [p2], has_more: false, next_cursor: null }
    : { items: [note('p1')], has_more: true, next_cursor: 'cur' }));
}

test('правка с версией: уходит version заметки', async () => {
  updateClientNote.mockResolvedValueOnce({});
  render(<ClientNotes studentUuid="c-1" />);
  const list = await screen.findByRole('list', { name: 'Заметки о клиенте' });
  userEvent.click(within(list).getByRole('button', { name: 'Изменить' }));
  const editor = screen.getByLabelText('Текст заметки');
  userEvent.clear(editor);
  userEvent.type(editor, 'Моя правка');
  userEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
  await waitFor(() => expect(updateClientNote).toHaveBeenCalledWith('c-1', 'n1', {
    content: 'Моя правка', noteType: 'general', version: 1,
  }));
  await waitFor(() => expect(screen.queryByLabelText('Текст заметки')).toBeNull());
});

test('409 у заметки со второй страницы: введённый текст остаётся, актуальная версия доступна', async () => {
  paged();
  updateClientNote.mockRejectedValueOnce(apiError(409));
  render(<ClientNotes studentUuid="c-1" />);
  await screen.findByText('Текст p1');
  userEvent.click(screen.getByRole('button', { name: 'Показать ещё' }));
  await screen.findByText('Текст p2');
  const row = screen.getAllByRole('listitem').find(li => within(li).queryByText('Текст p2'));
  userEvent.click(within(row).getByRole('button', { name: 'Изменить' }));
  const editor = screen.getByLabelText('Текст заметки');
  userEvent.clear(editor);
  userEvent.type(editor, 'Моя правка');
  paged(note('p2', { content: 'Чужая правка', version: 2 }));
  userEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

  expect(await screen.findByText('Чужая правка')).toBeInTheDocument();      // актуальная версия
  const orphan = screen.getByRole('region', { name: 'Несохранённые правки' });
  expect(within(orphan).getByLabelText('Текст заметки')).toHaveValue('Моя правка');
  expect(within(orphan).getByRole('alert')).toHaveTextContent(/Ваша правка сохранена/);
  expect(screen.getByText('Текст p1')).toBeInTheDocument();                 // список перечитан (стр. 1)

  // восстановление: сохранение поверх актуальной версии
  updateClientNote.mockResolvedValueOnce({});
  userEvent.click(within(orphan).getByRole('button', { name: 'Сохранить' }));
  await waitFor(() => expect(updateClientNote).toHaveBeenLastCalledWith('c-1', 'p2', {
    content: 'Моя правка', noteType: 'general', version: 2,
  }));
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Несохранённые правки' })).toBeNull());
});

test('перезагрузка списка черновик не трогает; «Отмена» убирает его', async () => {
  render(<ClientNotes studentUuid="c-1" />);
  const list = await screen.findByRole('list', { name: 'Заметки о клиенте' });
  userEvent.click(within(list).getByRole('button', { name: 'Изменить' }));
  userEvent.type(screen.getByLabelText('Текст заметки'), ' дополнение');
  createClientNote.mockResolvedValueOnce({});
  userEvent.type(screen.getByLabelText('Новая заметка'), 'Другая заметка');
  const callsBefore = getClientNotes.mock.calls.length;
  userEvent.click(screen.getByRole('button', { name: 'Сохранить заметку' }));
  await waitFor(() => expect(createClientNote).toHaveBeenCalled());
  await waitFor(() => expect(getClientNotes.mock.calls.length).toBeGreaterThan(callsBefore));
  await waitFor(() => expect(screen.getByLabelText('Текст заметки')).toHaveValue('Текст n1 дополнение'));
  userEvent.click(screen.getByRole('button', { name: 'Отмена' }));
  expect(screen.queryByLabelText('Текст заметки')).toBeNull();
});

test('смена клиента во время редактирования: черновик и правка клиента A не видны у B', async () => {
  getClientNotes.mockImplementation((uuid) => Promise.resolve(page([note(uuid === 'c-1' ? 'a1' : 'b1')])));
  const { rerender } = render(<ClientNotes studentUuid="c-1" />);
  await screen.findByText('Текст a1');
  userEvent.type(screen.getByLabelText('Новая заметка'), 'Черновик для A');
  userEvent.click(screen.getByRole('button', { name: 'Изменить' }));
  expect(screen.getByLabelText('Текст заметки')).toBeInTheDocument();

  rerender(<ClientNotes studentUuid="c-2" />);
  await screen.findByText('Текст b1');
  expect(screen.getByLabelText('Новая заметка')).toHaveValue('');
  expect(screen.queryByLabelText('Текст заметки')).toBeNull();
});

test('смена клиента во время сохранения: запоздалый ответ A не меняет форму и сообщения B', async () => {
  getClientNotes.mockImplementation((uuid) => Promise.resolve(page([note(uuid === 'c-1' ? 'a1' : 'b1')])));
  const save = deferred();
  createClientNote.mockReturnValueOnce(save.promise);
  const { rerender } = render(<ClientNotes studentUuid="c-1" />);
  await screen.findByText('Текст a1');
  userEvent.type(screen.getByLabelText('Новая заметка'), 'Для A');
  userEvent.click(screen.getByRole('button', { name: 'Сохранить заметку' }));

  rerender(<ClientNotes studentUuid="c-2" />);
  await screen.findByText('Текст b1');
  userEvent.type(screen.getByLabelText('Новая заметка'), 'Черновик B');
  save.reject(apiError(503));
  await waitFor(() => expect(createClientNote).toHaveBeenCalledTimes(1));
  await screen.findByText('Текст b1');
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getByLabelText('Новая заметка')).toHaveValue('Черновик B');
  expect(screen.getByRole('button', { name: 'Сохранить заметку' })).toBeEnabled();
});
