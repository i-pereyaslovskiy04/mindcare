import { act, renderHook, waitFor } from '@testing-library/react';
import * as chatApi from '../../../api/chat.api';
import { notifyMessagesUpdated } from '../../../features/chat/lib/messagesEvents';
import { usePsychologistChat } from './usePsychologistChat';

jest.mock('../../../api/chat.api');
jest.mock('../../../features/chat/lib/messagesEvents', () => ({
  notifyMessagesUpdated: jest.fn(),
}));

const activeConversation = {
  uuid: 'psych-active',
  student: { id: 7, full_name: 'Psych Active Student' },
  engagement_status: 'active',
  last_message_at: null,
  unread_count: 3,
  peer_is_online: true,
};

const archivedConversation = {
  uuid: 'psych-archived',
  student: { id: 8, full_name: 'Psych Archived Student' },
  engagement_status: 'completed',
  last_message_at: null,
  unread_count: 0,
  peer_is_online: false,
};

function apiMessage(id, overrides = {}) {
  return {
    id,
    uuid: `psych-message-${id}`,
    sender_id: 7,
    sender_role: 'student',
    is_mine: false,
    content: `psych message ${id}`,
    created_at: `2024-01-01T10:0${id}:00.000Z`,
    read_at: null,
    edited_at: null,
    is_deleted: false,
    ...overrides,
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function flushPromises() {
  await act(async () => {
    await Promise.resolve();
  });
}

function mockPsychologistList(items = [activeConversation]) {
  chatApi.getPsychologistConversations.mockResolvedValue({
    items,
    total: items.length,
    page: 1,
    size: 100,
  });
}

beforeEach(() => {
  jest.useRealTimers();
  jest.clearAllMocks();
  mockPsychologistList();
  chatApi.getPsychologistConversation.mockResolvedValue(activeConversation);
  chatApi.getPsychologistConversationMessages.mockResolvedValue({ items: [] });
  chatApi.markPsychologistConversationRead.mockResolvedValue({ updated_count: 1 });
  chatApi.sendPsychologistConversationMessage.mockResolvedValue(apiMessage(9, { is_mine: true }));
  chatApi.editPsychologistMessage.mockResolvedValue(apiMessage(9, { is_mine: true }));
  chatApi.deletePsychologistMessage.mockResolvedValue({});
});

afterEach(() => {
  jest.useRealTimers();
});

test('selectConversation loads messages and marks conversation as read', async () => {
  chatApi.getPsychologistConversationMessages.mockResolvedValue({
    items: [apiMessage(1), apiMessage(2, { read_at: '2024-01-01T10:03:00.000Z' })],
  });

  const { result } = renderHook(() => usePsychologistChat());

  await waitFor(() => expect(result.current.listLoading).toBe(false));

  act(() => {
    result.current.selectConversation(activeConversation.uuid);
  });

  await waitFor(() => expect(result.current.messages).toHaveLength(2));

  expect(chatApi.getPsychologistConversationMessages).toHaveBeenCalledWith(
    activeConversation.uuid,
    { limit: 100 },
  );
  expect(result.current.messages.map((m) => m.text)).toEqual([
    'psych message 1',
    'psych message 2',
  ]);
  expect(chatApi.markPsychologistConversationRead).toHaveBeenCalledWith(activeConversation.uuid);
  await waitFor(() => expect(notifyMessagesUpdated).toHaveBeenCalled());
  expect(result.current.conversations[0].unread_count).toBe(0);
});

test('does not apply stale messages after quick conversation switch', async () => {
  const slowA = deferred();
  const fastB = deferred();
  mockPsychologistList([
    { ...activeConversation, uuid: 'psych-a' },
    { ...activeConversation, uuid: 'psych-b' },
  ]);
  chatApi.getPsychologistConversationMessages.mockImplementation((uuid) => {
    if (uuid === 'psych-a') return slowA.promise;
    if (uuid === 'psych-b') return fastB.promise;
    return Promise.resolve({ items: [] });
  });

  const { result } = renderHook(() => usePsychologistChat());

  await waitFor(() => expect(result.current.listLoading).toBe(false));

  act(() => {
    result.current.selectConversation('psych-a');
    result.current.selectConversation('psych-b');
  });
  act(() => {
    fastB.resolve({ items: [apiMessage(2, { content: 'message from B' })] });
  });

  await waitFor(() => expect(result.current.messages.map((m) => m.text)).toEqual(['message from B']));

  act(() => {
    slowA.resolve({ items: [apiMessage(1, { content: 'stale message from A' })] });
  });
  await flushPromises();

  expect(result.current.selectedUuid).toBe('psych-b');
  expect(result.current.messages.map((m) => m.text)).toEqual(['message from B']);
});

test('polls messages only for active selected conversation', async () => {
  jest.useFakeTimers();
  chatApi.getPsychologistConversationMessages
    .mockResolvedValueOnce({ items: [apiMessage(1)] })
    .mockResolvedValueOnce({ items: [apiMessage(1), apiMessage(2, { content: 'polled message' })] });

  const { result } = renderHook(() => usePsychologistChat());

  await waitFor(() => expect(result.current.listLoading).toBe(false));
  act(() => {
    result.current.selectConversation(activeConversation.uuid);
  });
  await waitFor(() => expect(result.current.messages).toHaveLength(1));

  await act(async () => {
    jest.advanceTimersByTime(8000);
    await Promise.resolve();
  });

  await waitFor(() => expect(chatApi.getPsychologistConversationMessages).toHaveBeenCalledTimes(2));
  await waitFor(() =>
    expect(result.current.messages.map((m) => m.text)).toEqual([
      'psych message 1',
      'polled message',
    ]),
  );
});

test('does not start message polling for inactive/archive conversation', async () => {
  jest.useFakeTimers();
  mockPsychologistList([archivedConversation]);
  chatApi.getPsychologistConversationMessages.mockResolvedValue({ items: [apiMessage(1)] });

  const { result } = renderHook(() => usePsychologistChat());

  await waitFor(() => expect(result.current.listLoading).toBe(false));
  act(() => {
    result.current.selectConversation(archivedConversation.uuid);
  });
  await waitFor(() => expect(result.current.messages).toHaveLength(1));

  await act(async () => {
    jest.advanceTimersByTime(8000);
    await Promise.resolve();
  });

  expect(chatApi.getPsychologistConversationMessages).toHaveBeenCalledTimes(1);
});

test('psychologist send 409 refreshes the selected conversation status', async () => {
  const conflict = Object.assign(new Error('HTTP 409'), { status: 409 });
  chatApi.getPsychologistConversationMessages.mockResolvedValue({ items: [apiMessage(1)] });
  chatApi.sendPsychologistConversationMessage.mockRejectedValue(conflict);
  chatApi.getPsychologistConversation.mockResolvedValue({
    ...activeConversation,
    engagement_status: 'completed',
    last_message_at: '2024-01-01T10:09:00.000Z',
  });

  const { result } = renderHook(() => usePsychologistChat());

  await waitFor(() => expect(result.current.listLoading).toBe(false));
  act(() => {
    result.current.selectConversation(activeConversation.uuid);
  });
  await waitFor(() => expect(result.current.messages).toHaveLength(1));

  await act(async () => {
    await result.current.send('hello');
  });

  expect(result.current.sendError).toBe('Диалог закрыт');
  expect(chatApi.getPsychologistConversation).toHaveBeenCalledWith(activeConversation.uuid);
  await waitFor(() =>
    expect(result.current.selected).toMatchObject({
      engagement_status: 'completed',
      last_message_at: '2024-01-01T10:09:00.000Z',
    }),
  );
});

test('psychologist delete 409 calls getPsychologistConversation, updates conversation status, and keeps message', async () => {
  const msgToDelete = apiMessage(1, { sender_id: 10, sender_role: 'psychologist', is_mine: true });
  const conflict = Object.assign(new Error('HTTP 409'), { status: 409 });
  chatApi.getPsychologistConversationMessages.mockResolvedValue({ items: [msgToDelete] });
  chatApi.deletePsychologistMessage.mockRejectedValue(conflict);
  chatApi.getPsychologistConversation.mockResolvedValue({
    ...activeConversation,
    engagement_status: 'completed',
    last_message_at: '2024-01-01T10:09:00.000Z',
  });

  const { result } = renderHook(() => usePsychologistChat());

  await waitFor(() => expect(result.current.listLoading).toBe(false));
  act(() => {
    result.current.selectConversation(activeConversation.uuid);
  });
  await waitFor(() => expect(result.current.messages).toHaveLength(1));

  let deleteResult;
  await act(async () => {
    deleteResult = await result.current.deleteMessage(msgToDelete.uuid);
  });

  // delete отклонён → возвращает false, ставит ошибку
  expect(deleteResult).toBe(false);
  expect(result.current.sendError).toBe('Диалог закрыт');
  // 409 → точечный refresh через getPsychologistConversation
  expect(chatApi.getPsychologistConversation).toHaveBeenCalledWith(activeConversation.uuid);
  // conversation обновляется: engagement_status и last_message_at из свежего ответа
  await waitFor(() =>
    expect(result.current.selected).toMatchObject({
      engagement_status: 'completed',
      last_message_at: '2024-01-01T10:09:00.000Z',
    }),
  );
  // сообщение НЕ удалено из ленты: delete не был подтверждён сервером
  expect(result.current.messages).toHaveLength(1);
});
