import {
  deletePsychologistMessage,
  downloadPsychologistAttachment,
  editPsychologistMessage,
  getPsychologistConversation,
  getPsychologistConversationMessages,
  getPsychologistConversations,
  markPsychologistConversationRead,
  sendPsychologistConversationMessage,
  uploadPsychologistAttachment,
} from '../../../api/chat.api';
import { useChatCore } from '../../../features/chat/hooks/useChatCore';

/**
 * Диалоги психолога. Thin wrapper вокруг useChatCore.
 *
 * 409 Conflict → точечный refresh через getPsychologistConversation (getConversation).
 */
export function usePsychologistChat() {
  return useChatCore({
    listConversations: getPsychologistConversations,
    getMessages: getPsychologistConversationMessages,
    sendMessage: sendPsychologistConversationMessage,
    editMessage: editPsychologistMessage,
    deleteMessage: deletePsychologistMessage,
    markConversationRead: markPsychologistConversationRead,
    getConversation: getPsychologistConversation,
    listErrorMessage: 'Не удалось загрузить список бесед.',
    downloadAttachment: downloadPsychologistAttachment,
    uploadAttachment: uploadPsychologistAttachment,
  });
}
