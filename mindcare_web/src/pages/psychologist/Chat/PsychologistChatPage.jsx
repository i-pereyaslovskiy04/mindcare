import { useEffect, useRef, useState } from 'react';
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
    metaLoaded: sysMetaLoaded,
    refreshMeta: sysRefreshMeta,
    open: sysOpen,
    close: sysClose,
    pollNew: sysPollNew,
  } = useSystemConversation();

  const [systemSelected, setSystemSelected] = useState(false);
  const enteredRef = useRef(false);  // entrance-выбор делаем один раз

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

  // Entrance-выбор (один раз, после загрузки списка и метаданных системной беседы).
  // Приоритет: непрочитанная system-беседа → первый клиентский диалог с unread →
  // нет клиентов → system. Иначе оставляем дефолт хука (первый клиент). Ручной выбор
  // пользователя не перебиваем (enteredRef).
  useEffect(() => {
    if (enteredRef.current || listLoading || !sysMetaLoaded) return;
    enteredRef.current = true;
    if (sysConv && sysConv.unread_count > 0) {
      setSystemSelected(true);
      return;
    }
    const unreadConv = conversations.find((c) => c.unread_count > 0);
    if (unreadConv) {
      setSystemSelected(false);
      selectConversation(unreadConv.uuid);
    } else if (conversations.length === 0) {
      setSystemSelected(true);
    }
  }, [listLoading, sysMetaLoaded, sysConv, conversations, selectConversation]);

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
  } else {
    // Список: «Системные уведомления» закреплены сверху ВСЕГДА, затем клиентские диалоги.
    const contacts = [systemContact(sysConv), ...conversations.map(toContact)];

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
