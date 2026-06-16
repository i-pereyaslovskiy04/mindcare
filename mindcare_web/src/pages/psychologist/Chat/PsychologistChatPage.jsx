import { useEffect, useState } from 'react';
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

  const handleSelect = (id) => {
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
