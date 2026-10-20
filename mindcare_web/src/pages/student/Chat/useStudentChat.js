import {
  deleteStudentMessage,
  downloadStudentAttachment,
  editStudentMessage,
  getStudentConversationMessages,
  getStudentConversations,
  markStudentConversationRead,
  sendStudentConversationMessage,
  uploadStudentAttachment,
} from '../../../api/chat.api';
import { useChatCore } from '../../../features/chat/hooks/useChatCore';

/**
 * Диалоги студента (Stage 31t). Thin wrapper вокруг useChatCore.
 *
 * VK-like: вход НЕ открывает диалог и НЕ помечает прочитанным —
 * open/mark-read только по явному клику.
 * 409 Conflict → silent reload всего списка (getConversation: null).
 */
export function useStudentChat() {
  return useChatCore({
    listConversations: getStudentConversations,
    getMessages: getStudentConversationMessages,
    sendMessage: sendStudentConversationMessage,
    editMessage: editStudentMessage,
    deleteMessage: deleteStudentMessage,
    markConversationRead: markStudentConversationRead,
    getConversation: null,
    listErrorMessage: 'Не удалось загрузить список диалогов.',
    downloadAttachment: downloadStudentAttachment,
    uploadAttachment: uploadStudentAttachment,
  });
}
