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
const SYSTEM_MSG_POLL_MS = 8000;

export default function ChatPage() {
  const {
    conversation: engConv,
    messages: engMessages,
    loading: engLoading,
    error: engError,
    sending,
    sendError,
    send,
    refetch,
  } = useStudentChat();

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

  const [selected, setSelected] = useState(null);

  // Лёгкий poll метаданных системной беседы (unread в списке) независимо от выбора.
  useEffect(() => {
    sysRefreshMeta();
    const t = setInterval(sysRefreshMeta, SYSTEM_META_POLL_MS);
    return () => clearInterval(t);
  }, [sysRefreshMeta]);

  // Дефолтный выбор при входе (только пока ничего не выбрано вручную).
  // Приоритет: непрочитанная system-беседа → непрочитанный диалог с психологом →
  // обычный дефолт. Ждём загрузки engagement и первого refreshMeta системной беседы,
  // чтобы приоритет был детерминированным.
  useEffect(() => {
    if (selected != null || engLoading || !sysMetaLoaded) return;
    if (sysConv && sysConv.unread_count > 0) {
      setSelected(SYSTEM_DIALOG_ID);
    } else if (engConv && engConv.unread_count > 0) {
      setSelected(engConv.uuid);
    } else {
      setSelected(engConv ? engConv.uuid : SYSTEM_DIALOG_ID);
    }
  }, [selected, engLoading, sysMetaLoaded, sysConv, engConv]);

  // Открытие системной беседы: загрузка + mark-read + лёгкий poll новых.
  useEffect(() => {
    if (selected !== SYSTEM_DIALOG_ID) return undefined;
    sysOpen();
    const t = setInterval(sysPollNew, SYSTEM_MSG_POLL_MS);
    return () => {
      clearInterval(t);
      sysClose();
    };
  }, [selected, sysOpen, sysPollNew, sysClose]);

  const engClosed = Boolean(engConv) && engConv.engagement_status !== 'active';

  let body;
  if (engLoading) {
    body = (
      <div className={styles.stateBox}>
        <p className={styles.stateText}>Загрузка сообщений…</p>
      </div>
    );
  } else if (engError) {
    body = (
      <div className={styles.stateBox}>
        <p className={styles.stateText}>{engError}</p>
        <Button onClick={refetch}>Повторить</Button>
      </div>
    );
  } else {
    // Список: «Системные уведомления» закреплены сверху ВСЕГДА (даже без backend
    // conversation), затем диалог с психологом, если назначен.
    const contacts = [systemContact(sysConv)];
    if (engConv) {
      contacts.push({
        id: engConv.uuid,
        name: engConv.partner.full_name,
        initials: initialsOf(engConv.partner.full_name),
        role: engClosed ? 'Диалог закрыт' : 'Психолог',
        lastMsg: engClosed ? 'История доступна для чтения' : 'Ваш психолог',
        time: formatLastTime(engConv.last_message_at),
        unread: engConv.unread_count || 0,
      });
    }

    let pane;
    if (selected === SYSTEM_DIALOG_ID) {
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
    } else if (engConv) {
      pane = (
        <ChatWindow
          contact={{
            id: engConv.uuid,
            name: engConv.partner.full_name,
            initials: initialsOf(engConv.partner.full_name),
            role: engClosed ? 'Диалог закрыт' : 'Психолог',
          }}
          messages={engMessages}
          onSend={send}
          closed={engClosed}
          sending={sending}
          sendError={sendError}
        />
      );
    } else {
      pane = (
        <div className={styles.paneState}>
          <p className={styles.stateText}>Выберите диалог.</p>
        </div>
      );
    }

    body = (
      <div className={styles.shell}>
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
      <p className={styles.pageSub}>
        Связь с психологом между сессиями и системные уведомления. Для срочной помощи —
        телефон доверия в настройках.
      </p>

      {body}
    </div>
  );
}
