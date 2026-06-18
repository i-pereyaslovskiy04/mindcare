import { act, renderHook, waitFor } from '@testing-library/react';
import * as chatApi from '../../../api/chat.api';
import { notifyMessagesUpdated } from '../../../features/chat/lib/messagesEvents';
import { useStudentChat } from './useStudentChat';

jest.mock('../../../api/chat.api');
jest.mock('../../../features/chat/lib/messagesEvents', () => ({
  notifyMessagesUpdated: jest.fn(),
}));

const activeConversation = {
  uuid: 'student-active',
  partner: { id: 2, full_name: 'Student Active Peer' },
  engagement_status: 'active',
  last_message_at: null,
  unread_count: 2,
  peer_is_online: true,
};

const archivedConversation = {
  uuid: 'student-archived',
  partner: { id: 3, full_name: 'Student Archived Peer' },
  engagement_status: 'completed',
  last_message_at: null,
  unread_count: 0,
  peer_is_online: false,
};

function apiMessage(id, overrides = {}) {
  return {
    id,
    uuid: `student-message-${id}`,
    sender_id: 2,
    sender_role: 'psychologist',
    is_mine: false,
    content: `student message ${id}`,
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

function mockStudentList(items = [activeConversation]) {
  chatApi.getStudentConversations.mockResolvedValue({
    items,
    total: items.length,
    page: 1,
    size: 100,
  });
}

beforeEach(() => {
  jest.useRealTimers();
  jest.clearAllMocks();
  mockStudentList();
  chatApi.getStudentConversationMessages.mockResolvedValue({ items: [] });
  chatApi.markStudentConversationRead.mockResolvedValue({ updated_count: 1 });
  chatApi.sendStudentConversationMessage.mockResolvedValue(apiMessage(9, { is_mine: true }));
  chatApi.editStudentMessage.mockResolvedValue(apiMessage(9, { is_mine: true }));
  chatApi.deleteStudentMessage.mockResolvedValue({});
});

afterEach(() => {
  jest.useRealTimers();
});

test('selectConversation loads messages and marks conversation as read', async () => {
  chatApi.getStudentConversationMessages.mockResolvedValue({
    items: [apiMessage(1), apiMessage(2, { read_at: '2024-01-01T10:03:00.000Z' })],
  });

  const { result } = renderHook(() => useStudentChat());

  await waitFor(() => expect(result.current.listLoading).toBe(false));

  act(() => {
    result.current.selectConversation(activeConversation.uuid);
  });

  await waitFor(() => expect(result.current.messages).toHaveLength(2));

  expect(chatApi.getStudentConversationMessages).toHaveBeenCalledWith(
    activeConversation.uuid,
    { limit: 100 },
  );
  expect(result.current.messages.map((m) => m.text)).toEqual([
    'student message 1',
    'student message 2',
  ]);
  expect(chatApi.markStudentConversationRead).toHaveBeenCalledWith(activeConversation.uuid);
  await waitFor(() => expect(notifyMessagesUpdated).toHaveBeenCalled());
  expect(result.current.conversations[0].unread_count).toBe(0);
});

test('does not apply stale messages after quick conversation switch', async () => {
  const slowA = deferred();
  const fastB = deferred();
  mockStudentList([
    { ...activeConversation, uuid: 'student-a' },
    { ...activeConversation, uuid: 'student-b' },
  ]);
  chatApi.getStudentConversationMessages.mockImplementation((uuid) => {
    if (uuid === 'student-a') return slowA.promise;
    if (uuid === 'student-b') return fastB.promise;
    return Promise.resolve({ items: [] });
  });

  const { result } = renderHook(() => useStudentChat());

  await waitFor(() => expect(result.current.listLoading).toBe(false));

  act(() => {
    result.current.selectConversation('student-a');
    result.current.selectConversation('student-b');
  });
  act(() => {
    fastB.resolve({ items: [apiMessage(2, { content: 'message from B' })] });
  });

  await waitFor(() => expect(result.current.messages.map((m) => m.text)).toEqual(['message from B']));

  act(() => {
    slowA.resolve({ items: [apiMessage(1, { content: 'stale message from A' })] });
  });
  await flushPromises();

  expect(result.current.selectedUuid).toBe('student-b');
  expect(result.current.messages.map((m) => m.text)).toEqual(['message from B']);
});

test('polls messages only for active selected conversation', async () => {
  jest.useFakeTimers();
  chatApi.getStudentConversationMessages
    .mockResolvedValueOnce({ items: [apiMessage(1)] })
    .mockResolvedValueOnce({ items: [apiMessage(1), apiMessage(2, { content: 'polled message' })] });

  const { result } = renderHook(() => useStudentChat());

  await waitFor(() => expect(result.current.listLoading).toBe(false));
  act(() => {
    result.current.selectConversation(activeConversation.uuid);
  });
  await waitFor(() => expect(result.current.messages).toHaveLength(1));

  await act(async () => {
    jest.advanceTimersByTime(8000);
    await Promise.resolve();
  });

  await waitFor(() => expect(chatApi.getStudentConversationMessages).toHaveBeenCalledTimes(2));
  await waitFor(() =>
    expect(result.current.messages.map((m) => m.text)).toEqual([
      'student message 1',
      'polled message',
    ]),
  );
});

test('does not start message polling for inactive/archive conversation', async () => {
  jest.useFakeTimers();
  mockStudentList([archivedConversation]);
  chatApi.getStudentConversationMessages.mockResolvedValue({ items: [apiMessage(1)] });

  const { result } = renderHook(() => useStudentChat());

  await waitFor(() => expect(result.current.listLoading).toBe(false));
  act(() => {
    result.current.selectConversation(archivedConversation.uuid);
  });
  await waitFor(() => expect(result.current.messages).toHaveLength(1));

  await act(async () => {
    jest.advanceTimersByTime(8000);
    await Promise.resolve();
  });

  expect(chatApi.getStudentConversationMessages).toHaveBeenCalledTimes(1);
});

test('student send 409 falls back to silent list reload', async () => {
  const conflict = Object.assign(new Error('HTTP 409'), { status: 409 });
  chatApi.getStudentConversationMessages.mockResolvedValue({ items: [apiMessage(1)] });
  chatApi.sendStudentConversationMessage.mockRejectedValue(conflict);

  const { result } = renderHook(() => useStudentChat());

  await waitFor(() => expect(result.current.listLoading).toBe(false));
  act(() => {
    result.current.selectConversation(activeConversation.uuid);
  });
  await waitFor(() => expect(result.current.messages).toHaveLength(1));

  await act(async () => {
    await result.current.send('hello');
  });

  expect(result.current.sendError).toBe('Диалог закрыт');
  expect(chatApi.getStudentConversations).toHaveBeenCalledTimes(2);
});
