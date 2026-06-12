import Button from '../../../components/UI/Button/Button';
import ChatSidebar from '../../student/Chat/components/ChatSidebar';
import ChatWindow from '../../student/Chat/components/ChatWindow';
import { usePsychologistChat } from './usePsychologistChat';
import styles from './PsychologistChatPage.module.css';

function initialsOf(name) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('');
}

function formatLastTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString()
    ? d.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString('ru', { day: 'numeric', month: 'short' });
}

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

  const closed = Boolean(selected) && selected.engagement_status !== 'active';

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
  } else if (conversations.length === 0) {
    body = (
      <div className={styles.stateBox}>
        <p className={styles.stateTitle}>У вас пока нет активных клиентов для чата.</p>
        <p className={styles.stateText}>
          Когда супервизор назначит студента, беседа появится здесь.
        </p>
      </div>
    );
  } else {
    let pane;
    if (messagesError) {
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
        <ChatSidebar
          contacts={conversations.map(toContact)}
          activeId={selectedUuid}
          onSelect={selectConversation}
        />
        {pane}
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>
        Чат с <em>клиентами</em>
      </h1>
      <p className={styles.pageSub}>
        Переписка со студентами по активным консультационным связям. История закрытых
        диалогов доступна только для чтения.
      </p>

      {body}
    </div>
  );
}
