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
import { useStudentChat } from './useStudentChat';
import styles from './ChatPage.module.css';

const SYSTEM_META_POLL_MS = 30000;
const MSG_POLL_MS = 8000;

export default function ChatPage() {
  const {
    conversation: engConv,
    messages: engMessages,
    metaLoading: engMetaLoading,
    metaError: engMetaError,
    messagesLoading: engMsgLoading,
    messagesError: engMsgError,
    sending,
    sendError,
    refreshMeta: engRefreshMeta,
    open: engOpen,
    close: engClose,
    pollNew: engPollNew,
    send,
  } = useStudentChat();

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
  const [selected, setSelected] = useState(null);

  const engUuid = engConv?.uuid ?? null;
  const engActive = engConv?.engagement_status === 'active';
  const engClosed = Boolean(engConv) && !engActive;

  // Лёгкий poll метаданных системной беседы (unread в списке) независимо от выбора.
  useEffect(() => {
    sysRefreshMeta();
    const t = setInterval(sysRefreshMeta, SYSTEM_META_POLL_MS);
    return () => clearInterval(t);
  }, [sysRefreshMeta]);

  // Открытие диалога с психологом — ТОЛЬКО по явному выбору (mark-read внутри open).
  useEffect(() => {
    if (!engUuid || selected !== engUuid) return undefined;
    engOpen();
    const t = engActive ? setInterval(engPollNew, MSG_POLL_MS) : null;
    return () => {
      if (t) clearInterval(t);
      engClose();
    };
  }, [selected, engUuid, engActive, engOpen, engClose, engPollNew]);

  // Открытие системной беседы — ТОЛЬКО по явному выбору.
  useEffect(() => {
    if (selected !== SYSTEM_DIALOG_ID) return undefined;
    sysOpen();
    const t = setInterval(sysPollNew, MSG_POLL_MS);
    return () => {
      clearInterval(t);
      sysClose();
    };
  }, [selected, sysOpen, sysPollNew, sysClose]);

  let body;
  if (engMetaLoading) {
    body = (
      <div className={styles.stateBox}>
        <p className={styles.stateText}>Загрузка диалогов…</p>
      </div>
    );
  } else if (engMetaError) {
    body = (
      <div className={styles.stateBox}>
        <p className={styles.stateText}>{engMetaError}</p>
        <Button onClick={engRefreshMeta}>Повторить</Button>
      </div>
    );
  } else {
    // Диалог с психологом первым, «Системные уведомления» — всегда последними.
    const contacts = [];
    if (engConv) {
      contacts.push({
        id: engConv.uuid,
        name: engConv.partner.full_name,
        initials: initialsOf(engConv.partner.full_name),
        role: engClosed ? 'Диалог закрыт' : 'Психолог',
        lastMsg: engClosed ? 'История доступна для чтения' : 'Ваш психолог',
        time: formatLastTime(engConv.last_message_at),
        unread: engConv.unread_count || 0,
        online: Boolean(engConv.peer_is_online),
      });
    }
    contacts.push(systemContact(sysConv));

    let pane;
    if (selected === SYSTEM_DIALOG_ID) {
      if (sysError) {
        pane = <div className={styles.paneState}><p className={styles.stateText}>{sysError}</p></div>;
      } else if (sysLoading && sysMessages.length === 0) {
        pane = <div className={styles.paneState}><p className={styles.stateText}>Загрузка уведомлений…</p></div>;
      } else {
        pane = (
          <ChatWindow
            contact={systemContact(sysConv)}
            messages={sysMessages}
            readOnly
            readOnlyNotice={SYSTEM_NOTICE}
            emptyText="Пока нет системных уведомлений."
            onBack={() => setSelected(null)}
          />
        );
      }
    } else if (selected === engUuid && engConv) {
      if (engMsgError) {
        pane = (
          <div className={styles.paneState}>
            <p className={styles.stateText}>{engMsgError}</p>
            <Button onClick={engOpen}>Повторить</Button>
          </div>
        );
      } else if (engMsgLoading && engMessages.length === 0) {
        pane = <div className={styles.paneState}><p className={styles.stateText}>Загрузка сообщений…</p></div>;
      } else {
        pane = (
          <ChatWindow
            contact={{
              id: engConv.uuid,
              name: engConv.partner.full_name,
              initials: initialsOf(engConv.partner.full_name),
              role: engClosed ? 'Диалог закрыт' : 'Психолог',
              online: Boolean(engConv.peer_is_online),
            }}
            messages={engMessages}
            onSend={send}
            closed={engClosed}
            sending={sending}
            sendError={sendError}
            onBack={() => setSelected(null)}
          />
        );
      }
    } else {
      // Ничего не выбрано — нейтральный placeholder (VK-like), без mark-read.
      pane = (
        <div className={styles.paneState}>
          <p className={styles.stateTitle}>Выберите диалог, чтобы открыть переписку.</p>
          <p className={styles.stateText}>Непрочитанные диалоги отмечены в списке слева.</p>
        </div>
      );
    }

    // На узких экранах shell работает как Telegram/VK: список ИЛИ открытый чат.
    // threadOpen = выбран любой диалог (engagement или системный).
    const threadOpen = selected !== null;
    body = (
      <div className={`${styles.shell} ${threadOpen ? styles.threadOpen : ''}`}>
        <ChatSidebar contacts={contacts} activeId={selected} onSelect={setSelected} />
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
