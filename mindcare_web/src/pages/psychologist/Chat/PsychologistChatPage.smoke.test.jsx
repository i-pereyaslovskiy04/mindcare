import { render, screen, waitFor } from '@testing-library/react';
import { useSearchParams } from 'react-router-dom';
import * as chatApi from '../../../api/chat.api';
import PsychologistChatPage, { findConversationFromQuickChatQuery } from './PsychologistChatPage';

jest.mock('../../../api/chat.api');
jest.mock('react-router-dom', () => ({
  useSearchParams: jest.fn(),
}), { virtual: true });

// jsdom не реализует scrollIntoView (используется в MessageList при открытии чата).
beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

let currentSearch = '';
let setSearchParamsMock;

beforeEach(() => {
  currentSearch = '';
  setSearchParamsMock = jest.fn((next) => {
    currentSearch = new URLSearchParams(next).toString();
  });
  useSearchParams.mockImplementation(() => [
    new URLSearchParams(currentSearch),
    setSearchParamsMock,
  ]);
  chatApi.getPsychologistConversations.mockResolvedValue({
    items: [
      {
        uuid: 'conv-1',
        student: { id: 7, full_name: 'Анна Смирнова' },
        engagement_status: 'active',
        last_message_at: null,
        unread_count: 0,
        peer_is_online: true,
      },
      {
        uuid: 'conv-2',
        student: { id: 8, uuid: 'student-8', full_name: 'Иван Петров' },
        engagement_status: 'active',
        last_message_at: null,
        unread_count: 0,
        peer_is_online: false,
      },
    ],
    total: 2,
    page: 1,
    size: 100,
  });
  chatApi.getPsychologistConversation.mockResolvedValue({
    uuid: 'conv-1',
    student: { id: 7, full_name: 'Анна Смирнова' },
    engagement_status: 'active',
    last_message_at: null,
    unread_count: 0,
    peer_is_online: true,
  });
  chatApi.getPsychologistConversationMessages.mockResolvedValue({ items: [] });
  chatApi.markPsychologistConversationRead.mockResolvedValue({ updated_count: 0 });
  chatApi.sendPsychologistConversationMessage.mockResolvedValue({});
  chatApi.getSystemConversation.mockResolvedValue({ conversation: null });
  chatApi.getSystemMessages.mockResolvedValue({ items: [] });
  chatApi.markSystemConversationRead.mockResolvedValue({ updated_count: 0 });
});

function renderPage(query = '') {
  currentSearch = query;
  return render(<PsychologistChatPage />);
}

test('findConversationFromQuickChatQuery supports conversation uuid/id and student id/uuid', () => {
  const conversations = [
    { uuid: 'conv-1', id: 'legacy-conv-1', student: { id: 7, uuid: 'student-7' } },
    { uuid: 'conv-2', student_id: 8, student_uuid: 'student-8' },
    { uuid: 'conv-3', client: { id: 9, uuid: 'student-9' } },
    { uuid: 'sys-1', type: 'system', id: 7 },
  ];

  expect(findConversationFromQuickChatQuery(conversations, {
    conversationId: 'legacy-conv-1',
  })?.uuid).toBe('conv-1');
  expect(findConversationFromQuickChatQuery(conversations, {
    studentId: 'student-7',
  })?.uuid).toBe('conv-1');
  expect(findConversationFromQuickChatQuery(conversations, {
    studentId: '8',
  })?.uuid).toBe('conv-2');
  expect(findConversationFromQuickChatQuery(conversations, {
    studentId: 'student-9',
  })?.uuid).toBe('conv-3');
  expect(findConversationFromQuickChatQuery(conversations, {
    studentId: 'sys-1',
  })).toBeNull();
});

test('psychologist ChatPage renders conversation list + placeholder (no auto-open)', async () => {
  renderPage();
  // заголовок раздела
  expect(await screen.findByText('Сообщения')).toBeInTheDocument();
  // клиентский диалог и секция системных уведомлений в списке
  expect(await screen.findByText('Анна Смирнова')).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { level: 2, name: 'Системные уведомления' }),
  ).toBeInTheDocument();
  // VK-like: ничего не открыто — показан placeholder
  expect(
    screen.getByText('Выберите диалог, чтобы открыть переписку.'),
  ).toBeInTheDocument();
  expect(chatApi.getPsychologistConversationMessages).not.toHaveBeenCalled();
});

test('psychologist ChatPage opens conversation from conversation query after list load', async () => {
  renderPage('conversation=conv-2');

  expect(await screen.findByText('Иван Петров')).toBeInTheDocument();
  await waitFor(() => {
    expect(chatApi.getPsychologistConversationMessages).toHaveBeenCalledWith('conv-2', {
      limit: 100,
    });
  });
  await waitFor(() => {
    expect(setSearchParamsMock).toHaveBeenCalledWith({}, { replace: true });
  });
});

test('psychologist ChatPage opens matching student conversation from numeric student query', async () => {
  renderPage('student=7');

  expect(await screen.findByText('Анна Смирнова')).toBeInTheDocument();
  await waitFor(() => {
    expect(chatApi.getPsychologistConversationMessages).toHaveBeenCalledWith('conv-1', {
      limit: 100,
    });
  });
  expect(screen.queryByText('Диалог со студентом не найден.')).not.toBeInTheDocument();
});

test('psychologist ChatPage opens matching student conversation from student uuid query', async () => {
  renderPage('student=student-8');

  expect(await screen.findByText('Иван Петров')).toBeInTheDocument();
  await waitFor(() => {
    expect(chatApi.getPsychologistConversationMessages).toHaveBeenCalledWith('conv-2', {
      limit: 100,
    });
  });
});

test('psychologist ChatPage does not clear quick-open query before conversation list loads', async () => {
  let resolveList;
  chatApi.getPsychologistConversations.mockReturnValue(new Promise((resolve) => {
    resolveList = resolve;
  }));

  renderPage('student=7');

  expect(setSearchParamsMock).not.toHaveBeenCalled();

  resolveList({
    items: [
      {
        uuid: 'conv-1',
        student: { id: 7, full_name: 'Анна Смирнова' },
        engagement_status: 'active',
        last_message_at: null,
        unread_count: 0,
        peer_is_online: true,
      },
    ],
    total: 1,
    page: 1,
    size: 100,
  });

  await waitFor(() => {
    expect(chatApi.getPsychologistConversationMessages).toHaveBeenCalledWith('conv-1', {
      limit: 100,
    });
  });
  await waitFor(() => {
    expect(setSearchParamsMock).toHaveBeenCalledWith({}, { replace: true });
  });
});

test('psychologist ChatPage does not crash when quick-open query is not found', async () => {
  renderPage('student=999');

  expect(await screen.findByText('Диалог со студентом не найден.')).toBeInTheDocument();
  expect(screen.getByText('Выберите диалог, чтобы открыть переписку.')).toBeInTheDocument();
  expect(chatApi.getPsychologistConversationMessages).not.toHaveBeenCalled();
  expect(setSearchParamsMock).toHaveBeenCalledWith({}, { replace: true });
});
