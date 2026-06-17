import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import Button from '../../../components/UI/Button/Button';
import ChatSidebar from '../../../features/chat/components/ChatSidebar';
import ChatWindow from '../../../features/chat/components/ChatWindow';
import { useSystemConversation } from '../../../features/chat/hooks/useSystemConversation';
import {
  SYSTEM_DIALOG_ID,
  SYSTEM_NOTICE,
  formatLastTime,
  initialsOf,
  splitConversations,
  systemContact,
} from '../../../features/chat/lib/conversationView';
import { usePsychologistChat } from './usePsychologistChat';
import styles from './PsychologistChatPage.module.css';

const SYSTEM_META_POLL_MS = 30000;
const SYSTEM_MSG_POLL_MS = 8000;

function sameParamValue(value, queryValue) {
  return value !== undefined && value !== null && String(value) === queryValue;
}

function matchesStudentQuery(conv, studentQuery) {
  const student = conv.student ?? {};
  const client = conv.client ?? {};
  const user = conv.user ?? {};
  const participant = conv.participant ?? {};
  return (
    sameParamValue(student.uuid, studentQuery) ||
    sameParamValue(student.id, studentQuery) ||
    sameParamValue(conv.student_uuid, studentQuery) ||
    sameParamValue(conv.student_id, studentQuery) ||
    sameParamValue(conv.studentUuid, studentQuery) ||
    sameParamValue(conv.studentId, studentQuery) ||
    sameParamValue(client.uuid, studentQuery) ||
    sameParamValue(client.id, studentQuery) ||
    sameParamValue(conv.client_uuid, studentQuery) ||
    sameParamValue(conv.client_id, studentQuery) ||
    sameParamValue(conv.clientUuid, studentQuery) ||
    sameParamValue(conv.clientId, studentQuery) ||
    sameParamValue(user.uuid, studentQuery) ||
    sameParamValue(user.id, studentQuery) ||
    sameParamValue(conv.user_uuid, studentQuery) ||
    sameParamValue(conv.user_id, studentQuery) ||
    sameParamValue(conv.userUuid, studentQuery) ||
    sameParamValue(conv.userId, studentQuery) ||
    sameParamValue(participant.uuid, studentQuery) ||
    sameParamValue(participant.id, studentQuery)
  );
}

function isSystemConversation(conv) {
  return conv?.type === 'system' || conv?.system === true;
}

export function findConversationFromQuickChatQuery(
  conversations,
  { conversationId, studentId },
) {
  if (!Array.isArray(conversations)) return null;
  const userConversations = conversations.filter((conv) => !isSystemConversation(conv));

  if (conversationId) {
    return userConversations.find((conv) => (
      sameParamValue(conv.uuid, conversationId) ||
      sameParamValue(conv.id, conversationId)
    )) ?? null;
  }

  if (studentId) {
    return userConversations.find((conv) => matchesStudentQuery(conv, studentId)) ?? null;
  }

  return null;
}

function toContact(conv) {
  const closed = conv.engagement_status !== 'active';
  return {
    id: conv.uuid,
    name: conv.student.full_name,
    initials: initialsOf(conv.student.full_name),
    role: closed ? 'Диалог закрыт' : 'Студент',
    authorRole: 'пациент',
    lastMsg: closed ? 'Диалог закрыт' : 'Активный диалог',
    time: formatLastTime(conv.last_message_at),
    unread: conv.unread_count,
    online: Boolean(conv.peer_is_online),
  };
}

export default function PsychologistChatPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    conversations,
    listLoading,
    listError,
    reloadList,
    selected,
    selectedUuid,
    selectConversation,
    deselect,
    messages,
    messagesLoading,
    messagesError,
    reloadMessages,
    sending,
    sendError,
    send,
    editMessage,
    deleteMessage,
    downloadAttachment,
  } = usePsychologistChat();

  const {
    conversation: sysConv,
    messages: sysMessages,
    loading: sysLoading,
    error: sysError,
    refreshMeta: sysRefreshMeta,
    open: sysOpen,
    close: sysClose,
    pollNew: sysPollNew,
  } = useSystemConversation();

  // VK-like: при входе ничего не выбрано и ничего не открыто (нет авто-mark-read).
  const [systemSelected, setSystemSelected] = useState(false);
  const [quickOpenError, setQuickOpenError] = useState('');
  const [quickOpenTargetUuid, setQuickOpenTargetUuid] = useState(null);

  const queryConversation = searchParams.get('conversation');
  const queryStudent = searchParams.get('student');
  const hasQuickOpenQuery = Boolean(queryConversation || queryStudent);

  // Лёгкий poll метаданных системной беседы (unread в списке).
  useEffect(() => {
    sysRefreshMeta();
    const t = setInterval(sysRefreshMeta, SYSTEM_META_POLL_MS);
    return () => clearInterval(t);
  }, [sysRefreshMeta]);

  // Открытие системной беседы — ТОЛЬКО по явному выбору: загрузка + mark-read + poll.
  useEffect(() => {
    if (!systemSelected) return undefined;
    sysOpen();
    const t = setInterval(sysPollNew, SYSTEM_MSG_POLL_MS);
    return () => {
      clearInterval(t);
      sysClose();
    };
  }, [systemSelected, sysOpen, sysPollNew, sysClose]);

  useEffect(() => {
    if (!hasQuickOpenQuery) return;

    if (listLoading) return;

    const target = findConversationFromQuickChatQuery(conversations, {
      conversationId: queryConversation,
      studentId: queryStudent,
    });

    if (target) {
      setQuickOpenError('');
      setSystemSelected(false);
      setQuickOpenTargetUuid(target.uuid);
      if (selectedUuid !== target.uuid) selectConversation(target.uuid);
    } else {
      setQuickOpenTargetUuid(null);
      setQuickOpenError('Диалог со студентом не найден.');
      setSearchParams({}, { replace: true });
    }
  }, [
    conversations,
    hasQuickOpenQuery,
    listLoading,
    queryConversation,
    queryStudent,
    selectConversation,
    selectedUuid,
    setSearchParams,
  ]);

  useEffect(() => {
    if (!quickOpenTargetUuid || selectedUuid !== quickOpenTargetUuid) return;
    setQuickOpenTargetUuid(null);
    setSearchParams({}, { replace: true });
  }, [quickOpenTargetUuid, selectedUuid, setSearchParams]);

  const handleSelect = (id) => {
    setQuickOpenError('');
    setQuickOpenTargetUuid(null);
    if (id === SYSTEM_DIALOG_ID) {
      setSystemSelected(true);
      return;
    }
    setSystemSelected(false);
    selectConversation(id);
  };

  // mobile back к списку: снять выбор и обычного, и системного диалога.
  const handleBack = () => {
    setSystemSelected(false);
    deselect();
  };

  const closed = Boolean(selected) && selected.engagement_status !== 'active';
  const activeId = systemSelected ? SYSTEM_DIALOG_ID : selectedUuid;
  // threadOpen = открыт любой диалог (обычный или системный) — для mobile list/thread.
  const threadOpen = systemSelected || Boolean(selectedUuid);

  let body;
  if (listLoading) {
    body = (
      <div className={styles.stateBox}>
        <p className={styles.stateText}>Загрузка чатов…</p>
      </div>
    );
  } else if (listError) {
    body = (
      <div className={styles.stateBox}>
        <p className={styles.stateText}>{listError}</p>
        <Button onClick={() => reloadList()}>Повторить</Button>
      </div>
    );
  } else {
    // Группировка (Stage 31s): архив (закрытые с историей) — сверху и свёрнут;
    // активные диалоги — в основном списке; «Системные уведомления» — последними.
    const { archived, active } = splitConversations(conversations);
    const archivedContacts = archived.map(toContact);
    const contacts = [...active.map(toContact), systemContact(sysConv)];

    let pane;
    if (systemSelected) {
      if (sysError) {
        pane = (
          <div className={styles.paneState}>
            <p className={styles.stateText}>{sysError}</p>
          </div>
        );
      } else if (sysLoading && sysMessages.length === 0) {
        pane = (
          <div className={styles.paneState}>
            <p className={styles.stateText}>Загрузка уведомлений…</p>
          </div>
        );
      } else {
        pane = (
          <ChatWindow
            contact={systemContact(sysConv)}
            messages={sysMessages}
            readOnly
            readOnlyNotice={SYSTEM_NOTICE}
            emptyText="Пока нет системных уведомлений."
            onBack={handleBack}
          />
        );
      }
    } else if (!selectedUuid) {
      // Ничего не выбрано — нейтральный placeholder (VK-like), без mark-read.
      pane = (
        <div className={styles.paneState}>
          {quickOpenError && <p className={styles.stateText}>{quickOpenError}</p>}
          <p className={styles.stateTitle}>Выберите диалог, чтобы открыть переписку.</p>
          <p className={styles.stateText}>Непрочитанные диалоги отмечены в списке слева.</p>
        </div>
      );
    } else if (messagesError) {
      pane = (
        <div className={styles.paneState}>
          <p className={styles.stateText}>{messagesError}</p>
          <Button onClick={reloadMessages}>Повторить</Button>
        </div>
      );
    } else if (!selected || (messagesLoading && messages.length === 0)) {
      pane = (
        <div className={styles.paneState}>
          <p className={styles.stateText}>Загрузка сообщений…</p>
        </div>
      );
    } else {
      pane = (
        <ChatWindow
          contact={toContact(selected)}
          messages={messages}
          onSend={send}
          onEdit={editMessage}
          onDelete={deleteMessage}
          closed={closed}
          sending={sending}
          sendError={sendError}
          onBack={handleBack}
          onDownloadAttachment={downloadAttachment}
        />
      );
    }

    body = (
      <div className={`${styles.shell} ${threadOpen ? styles.threadOpen : ''}`}>
        <ChatSidebar
          contacts={contacts}
          archivedContacts={archivedContacts}
          activeId={activeId}
          onSelect={handleSelect}
        />
        {pane}
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>
        <em>Сообщения</em>
      </h1>

      {body}
    </div>
  );
}
