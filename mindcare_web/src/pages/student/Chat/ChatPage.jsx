import { useState, useCallback } from 'react';
import ChatSidebar from './components/ChatSidebar';
import ChatWindow from './components/ChatWindow';
import styles from './ChatPage.module.css';

const CONTACTS = [
  {
    id: 1,
    name: 'Мария Ковалёва',
    initials: 'МК',
    role: 'Клинический психолог',
    lastMsg: 'Это хороший прогресс. Давайте…',
    time: '09:31',
    unread: 1,
    online: true,
  },
  {
    id: 2,
    name: 'Поддержка ДонГУ',
    initials: 'ПС',
    role: 'Техническая поддержка',
    lastMsg: 'Документы отправлены',
    time: 'вчера',
    unread: 0,
    online: false,
  },
  {
    id: 3,
    name: 'Группа «Спокойствие»',
    initials: 'ГС',
    role: 'Групповой чат',
    lastMsg: '5 сообщений',
    time: 'пн',
    unread: 0,
    online: false,
  },
];

const INITIAL_MESSAGES = {
  1: [
    { id: 1, text: 'Доброе утро, Анна. Как прошёл вечер?', sender: 'psychologist', time: '09:14' },
    { id: 2, text: 'Спасибо, лучше, чем боялась. Сделала упражнение на дыхание перед сном.', sender: 'me', time: '09:22' },
    { id: 3, text: 'Замечательно. А сон — был спокойнее?', sender: 'psychologist', time: '09:24' },
    { id: 4, text: 'Проснулась один раз, но быстро уснула обратно.', sender: 'me', time: '09:26' },
    { id: 5, text: 'Это хороший прогресс. Давайте на сессии в пятницу посмотрим, что именно помогло.', sender: 'psychologist', time: '09:31' },
  ],
  2: [
    { id: 1, text: 'Ваши документы были успешно отправлены. Ожидайте ответа в течение 2 рабочих дней.', sender: 'psychologist', time: 'вчера' },
  ],
  3: [
    { id: 1, text: 'Добро пожаловать в группу поддержки «Спокойствие»! Здесь вы можете делиться переживаниями.', sender: 'psychologist', time: 'пн' },
  ],
};

export default function ChatPage() {
  const [activeId, setActiveId] = useState(1);
  const [messages, setMessages] = useState(INITIAL_MESSAGES);

  const handleSend = useCallback(
    (text) => {
      const now = new Date().toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
      const newMsg = { id: Date.now(), text, sender: 'me', time: now };
      setMessages((prev) => ({
        ...prev,
        [activeId]: [...(prev[activeId] ?? []), newMsg],
      }));
    },
    [activeId],
  );

  const activeContact = CONTACTS.find((c) => c.id === activeId);

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>
        Чат с <em>психологом</em>
      </h1>
      <p className={styles.pageSub}>
        Связь между сессиями. Отвечаем в течение рабочего дня. Для срочной помощи — телефон доверия в настройках.
      </p>

      <div className={styles.shell}>
        <ChatSidebar contacts={CONTACTS} activeId={activeId} onSelect={setActiveId} />
        <ChatWindow
          contact={activeContact}
          messages={messages[activeId] ?? []}
          onSend={handleSend}
        />
      </div>
    </div>
  );
}
