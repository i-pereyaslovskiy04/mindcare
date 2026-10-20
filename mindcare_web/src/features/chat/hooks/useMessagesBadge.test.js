import { renderHook, waitFor } from '@testing-library/react';
import { useMessagesBadge } from './useMessagesBadge';
import * as chatApi from '../../../api/chat.api';
import * as AuthContext from '../../auth/AuthContext';

jest.mock('../../../api/chat.api');
// factory-мок, чтобы НЕ загружать реальный AuthContext (он импортирует
// react-router-dom, который jest-резолвер в этом проекте не находит).
jest.mock('../../auth/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../lib/messagesEvents', () => ({
  subscribeMessagesUpdated: () => () => {},
}));

beforeEach(() => {
  jest.clearAllMocks();
  // multi-role пользователь — но поведение badge зависит от аргумента role.
  AuthContext.useAuth.mockReturnValue({ user: { roles: ['student', 'psychologist'] } });
  chatApi.getSystemConversation.mockResolvedValue({ conversation: { unread_count: 0 } });
  chatApi.getStudentConversations.mockResolvedValue({
    items: [{ unread_count: 2 }, { unread_count: 0 }],
  });
  chatApi.getPsychologistConversations.mockResolvedValue({
    items: [{ unread_count: 1 }],
  });
});

test("role='student' hits the student conversations endpoint only", async () => {
  const { result } = renderHook(() => useMessagesBadge('student'));
  await waitFor(() => expect(result.current).toBe(1)); // 1 student dialog unread
  expect(chatApi.getStudentConversations).toHaveBeenCalled();
  expect(chatApi.getPsychologistConversations).not.toHaveBeenCalled();
});

test("role='psychologist' hits the psychologist conversations endpoint only", async () => {
  const { result } = renderHook(() => useMessagesBadge('psychologist'));
  await waitFor(() => expect(result.current).toBe(1));
  expect(chatApi.getPsychologistConversations).toHaveBeenCalled();
  expect(chatApi.getStudentConversations).not.toHaveBeenCalled();
});

test('other roles (supervisor/admin) produce 0 and hit no chat endpoints', async () => {
  const { result } = renderHook(() => useMessagesBadge('supervisor'));
  await waitFor(() => expect(result.current).toBe(0));
  expect(chatApi.getStudentConversations).not.toHaveBeenCalled();
  expect(chatApi.getPsychologistConversations).not.toHaveBeenCalled();
});

test.each(['student', 'psychologist'])(
  "role='%s': системная беседа в badge «Сообщения» не входит, личные unread остаются",
  async (role) => {
    // У системной беседы есть непрочитанные — их показывает колокольчик шапки.
    chatApi.getSystemConversation.mockResolvedValue({ conversation: { unread_count: 5 } });
    const { result } = renderHook(() => useMessagesBadge(role));
    await waitFor(() => expect(result.current).toBe(1)); // только личный диалог
    expect(chatApi.getSystemConversation).not.toHaveBeenCalled();
  },
);

test('без личных непрочитанных badge 0, даже если в системной беседе есть новые', async () => {
  chatApi.getSystemConversation.mockResolvedValue({ conversation: { unread_count: 3 } });
  chatApi.getStudentConversations.mockResolvedValue({ items: [{ unread_count: 0 }] });
  const { result } = renderHook(() => useMessagesBadge('student'));
  await waitFor(() => expect(chatApi.getStudentConversations).toHaveBeenCalled());
  await waitFor(() => expect(result.current).toBe(0));
  expect(chatApi.getSystemConversation).not.toHaveBeenCalled();
});
