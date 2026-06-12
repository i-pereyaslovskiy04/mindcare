import Button from '../../../components/UI/Button/Button';
import ChatSidebar from './components/ChatSidebar';
import ChatWindow from './components/ChatWindow';
import { useStudentChat } from './useStudentChat';
import styles from './ChatPage.module.css';

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

export default function ChatPage() {
  const { conversation, messages, loading, error, sending, sendError, send, refetch } =
    useStudentChat();

  const closed = Boolean(conversation) && conversation.engagement_status !== 'active';

  let body;
  if (loading) {
    body = (
      <div className={styles.stateBox}>
        <p className={styles.stateText}>Загрузка чата…</p>
      </div>
    );
  } else if (error) {
    body = (
      <div className={styles.stateBox}>
        <p className={styles.stateText}>{error}</p>
        <Button onClick={refetch}>Повторить</Button>
      </div>
    );
  } else if (!conversation) {
    body = (
      <div className={styles.stateBox}>
        <p className={styles.stateTitle}>Вам ещё не назначен психолог.</p>
        <p className={styles.stateText}>
          Когда специалист будет назначен, здесь появится чат.
        </p>
      </div>
    );
  } else {
    const contact = {
      id: conversation.uuid,
      name: conversation.partner.full_name,
      initials: initialsOf(conversation.partner.full_name),
      role: closed ? 'Диалог закрыт' : 'Психолог',
      lastMsg: closed ? 'История доступна для чтения' : 'Ваш психолог',
      time: formatLastTime(conversation.last_message_at),
      unread: 0,
    };
    body = (
      <div className={styles.shell}>
        <ChatSidebar contacts={[contact]} activeId={contact.id} onSelect={() => {}} />
        <ChatWindow
          contact={contact}
          messages={messages}
          onSend={send}
          closed={closed}
          sending={sending}
          sendError={sendError}
        />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>
        Чат с <em>психологом</em>
      </h1>
      <p className={styles.pageSub}>
        Связь между сессиями. Отвечаем в течение рабочего дня. Для срочной помощи — телефон доверия в настройках.
      </p>

      {body}
    </div>
  );
}
