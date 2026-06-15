import { render, screen, fireEvent } from '@testing-library/react';
import * as chatApi from '../../../api/chat.api';
import ChatPage from './ChatPage';

jest.mock('../../../api/chat.api');

// jsdom не реализует scrollIntoView (используется в MessageList) — полифилл.
beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

beforeEach(() => {
  chatApi.getMyConversation.mockResolvedValue({
    conversation: {
      uuid: 'eng-1',
      partner: { id: 2, full_name: 'Иван Петров' },
      engagement_status: 'active',
      last_message_at: null,
      unread_count: 0,
      peer_is_online: true,
    },
  });
  chatApi.getMyConversationMessages.mockResolvedValue({
    items: [
      {
        id: 1,
        uuid: 'm1',
        sender_id: 2,
        sender_role: 'psychologist',
        is_mine: false,
        content: 'Здравствуйте',
        created_at: new Date().toISOString(),
        read_at: null,
      },
    ],
  });
  chatApi.sendMyConversationMessage.mockResolvedValue({});
  chatApi.markMyConversationRead.mockResolvedValue({ updated_count: 0 });
  chatApi.getSystemConversation.mockResolvedValue({ conversation: null });
  chatApi.getSystemMessages.mockResolvedValue({ items: [] });
  chatApi.markSystemConversationRead.mockResolvedValue({ updated_count: 0 });
});

test('student ChatPage renders dialog list (list mode)', async () => {
  render(<ChatPage />);
  expect(await screen.findByText('Иван Петров')).toBeInTheDocument();
  expect(screen.getByText('Системные уведомления')).toBeInTheDocument();
});

test('student ChatPage opens thread (back button path) without crashing', async () => {
  render(<ChatPage />);
  const item = await screen.findByText('Иван Петров');
  fireEvent.click(item);
  // шапка чата с back-кнопкой + сообщение собеседника
  expect(await screen.findByLabelText('Назад к списку диалогов')).toBeInTheDocument();
  expect(await screen.findByText('Здравствуйте')).toBeInTheDocument();
});
