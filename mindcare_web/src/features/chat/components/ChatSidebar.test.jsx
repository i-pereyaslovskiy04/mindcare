import { render, screen, fireEvent, within } from '@testing-library/react';
import ChatSidebar from './ChatSidebar';

const active = [
  { id: 'a1', name: 'Сидорова Анна', initials: 'СА', role: 'Психолог', lastMsg: 'Ваш психолог', time: '', unread: 0 },
];
const system = {
  id: '__system__', system: true, name: 'Системные уведомления',
  initials: '', role: 'Системные уведомления', lastMsg: 'Уведомления MindCare', time: '', unread: 0,
};
const archived = [
  { id: 'z1', name: 'Иванова Мария', initials: 'ИМ', role: 'Диалог закрыт', lastMsg: 'История доступна для чтения', time: '', unread: 0 },
  { id: 'z2', name: 'Петров Алексей', initials: 'ПА', role: 'Диалог закрыт', lastMsg: 'История доступна для чтения', time: '', unread: 3 },
];

function setup(props = {}) {
  const onSelect = jest.fn();
  render(
    <ChatSidebar
      contacts={props.contacts ?? [...active, system]}
      archivedContacts={props.archivedContacts ?? archived}
      activeId={props.activeId ?? null}
      onSelect={onSelect}
    />,
  );
  return { onSelect };
}

// A. Все три секции рендерятся и в правильном порядке.
test('renders Архив / Сообщения / Системные уведомления sections in order', () => {
  setup();
  const archiveBtn = screen.getByRole('button', { name: /Архив/ });
  const msgHeader = screen.getByRole('heading', { name: 'Сообщения' });
  const sysHeader = screen.getByRole('heading', { name: 'Системные уведомления' });

  expect(archiveBtn).toBeInTheDocument();
  expect(msgHeader).toBeInTheDocument();
  expect(sysHeader).toBeInTheDocument();

  // порядок в DOM: Архив → Сообщения → Системные уведомления
  // eslint-disable-next-line testing-library/no-node-access
  expect(archiveBtn.compareDocumentPosition(msgHeader) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  // eslint-disable-next-line testing-library/no-node-access
  expect(msgHeader.compareDocumentPosition(sysHeader) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

// B. Архив свёрнут по умолчанию; active и system видны.
test('archive collapsed by default; active and system visible', () => {
  setup();
  expect(screen.getByRole('button', { name: /Архив/ })).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByText('Иванова Мария')).not.toBeInTheDocument();
  expect(screen.getByText('Сидорова Анна')).toBeInTheDocument();
  // system-карточка (вторичный текст уникален) видна
  expect(screen.getByText('Уведомления MindCare')).toBeInTheDocument();
});

// C. Клик по «Архив» раскрывает архивные диалоги и не выбирает диалог.
test('clicking archive expands archived dialogs without selecting', () => {
  const { onSelect } = setup();
  fireEvent.click(screen.getByRole('button', { name: /Архив/ }));
  expect(screen.getByText('Иванова Мария')).toBeInTheDocument();
  expect(screen.getByText('Петров Алексей')).toBeInTheDocument();
  expect(onSelect).not.toHaveBeenCalled();
});

// D. System-карточка кликабельна и выбирается общей логикой (onSelect по id).
test('system conversation is a normal selectable card (shared select logic)', () => {
  const { onSelect } = setup();
  fireEvent.click(screen.getByText('Уведомления MindCare'));
  expect(onSelect).toHaveBeenCalledWith('__system__');
});

// E. Нет архива → секция «Архив» не рендерится; «Сообщения» и «Системные» есть.
test('no archive section when no archived dialogs', () => {
  setup({ archivedContacts: [] });
  expect(screen.queryByRole('button', { name: /Архив/ })).not.toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Сообщения' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Системные уведомления' })).toBeInTheDocument();
});

// F. Нет активных диалогов → секция system всё равно показывается.
test('system section still shown when no active dialogs', () => {
  setup({ contacts: [system], archivedContacts: [] });
  expect(screen.queryByRole('heading', { name: 'Сообщения' })).not.toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Системные уведомления' })).toBeInTheDocument();
  expect(screen.getByText('Уведомления MindCare')).toBeInTheDocument();
});

// Архивный unread агрегируется на заголовке «Архив».
test('archive header shows aggregated unread', () => {
  setup();
  const archiveBtn = screen.getByRole('button', { name: /Архив/ });
  expect(within(archiveBtn).getByText('3')).toBeInTheDocument();   // 0 + 3
});
