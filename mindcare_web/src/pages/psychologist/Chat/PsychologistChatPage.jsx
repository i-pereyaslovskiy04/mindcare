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
    lastMsg: closed ? 'Диалог закрыт' : 'Активный диалог',
    time: formatLastTime(conv.last_message_at),
    unread: conv.unread_count,
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
    messages,
    messagesLoading,
    messagesError,
    reloadMessages,
    sending,
    sendError,
    send,
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

  const [systemSelected, setSystemSelected] = useState(false);

  // Лёгкий poll метаданных системной беседы (unread в списке).
  useEffect(() => {
    sysRefreshMeta();
    const t = setInterval(sysRefreshMeta, SYSTEM_META_POLL_MS);
    return () => clearInterval(t);
  }, [sysRefreshMeta]);

  // Открытие системной беседы: загрузка + mark-read + лёгкий poll новых.
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

  const closed = Boolean(selected) && selected.engagement_status !== 'active';
  const activeId = systemSelected ? SYSTEM_DIALOG_ID : selectedUuid;

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
  } else if (conversations.length === 0 && !sysConv) {
    body = (
      <div className={styles.stateBox}>
        <p className={styles.stateTitle}>У вас пока нет активных клиентов для чата.</p>
        <p className={styles.stateText}>
          Когда супервизор назначит студента, беседа появится здесь.
        </p>
      </div>
    );
  } else {
    // Список: системные уведомления закреплены сверху, затем клиентские диалоги.
    const contacts = [];
    if (sysConv) contacts.push(systemContact(sysConv));
    contacts.push(...conversations.map(toContact));

    let pane;
    if (systemSelected && sysConv) {
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
          />
        );
      }
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
          <p className={styles.stateText}>
            {selected ? 'Загрузка сообщений…' : 'Выберите диалог.'}
          </p>
        </div>
      );
    } else {
      pane = (
        <ChatWindow
          contact={toContact(selected)}
          messages={messages}
          onSend={send}
          closed={closed}
          sending={sending}
          sendError={sendError}
        />
      );
    }

    body = (
      <div className={styles.shell}>
        <ChatSidebar contacts={contacts} activeId={activeId} onSelect={handleSelect} />
        {pane}
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>
        <em>Сообщения</em>
      </h1>
      <p className={styles.pageSub}>
        Переписка со студентами по активным консультационным связям и системные
        уведомления. История закрытых диалогов доступна только для чтения.
      </p>

      {body}
    </div>
  );
}
