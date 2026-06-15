import { render, screen } from '@testing-library/react';
import * as chatApi from '../../../api/chat.api';
import PsychologistChatPage from './PsychologistChatPage';

jest.mock('../../../api/chat.api');

// jsdom не реализует scrollIntoView (используется в MessageList при открытии чата).
beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

beforeEach(() => {
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
    ],
    total: 1,
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

test('psychologist ChatPage renders conversation list + placeholder (no auto-open)', async () => {
  render(<PsychologistChatPage />);
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
});
