import { render, screen, waitFor } from '@testing-library/react';
import { useSearchParams } from 'react-router-dom';
import * as chatApi from '../../../api/chat.api';
import PsychologistChatPage from './PsychologistChatPage';

jest.mock('../../../api/chat.api');
jest.mock('react-router-dom', () => ({
  useSearchParams: jest.fn(),
}), { virtual: true });

// jsdom не реализует scrollIntoView (используется в MessageList при открытии чата).
beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

beforeEach(() => {
  useSearchParams.mockReturnValue([new URLSearchParams(''), jest.fn()]);
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
        student: { id: 8, full_name: 'Иван Петров' },
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
  useSearchParams.mockReturnValue([new URLSearchParams(query), jest.fn()]);
  return render(<PsychologistChatPage />);
}

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
});

test('psychologist ChatPage opens matching student conversation from student query', async () => {
  renderPage('student=7');

  expect(await screen.findByText('Анна Смирнова')).toBeInTheDocument();
  await waitFor(() => {
    expect(chatApi.getPsychologistConversationMessages).toHaveBeenCalledWith('conv-1', {
      limit: 100,
    });
  });
});

test('psychologist ChatPage does not crash when quick-open query is not found', async () => {
  renderPage('student=999');

  expect(await screen.findByText('Диалог со студентом не найден.')).toBeInTheDocument();
  expect(screen.getByText('Выберите диалог, чтобы открыть переписку.')).toBeInTheDocument();
  expect(chatApi.getPsychologistConversationMessages).not.toHaveBeenCalled();
});
