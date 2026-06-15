import { render, screen, fireEvent, within } from '@testing-library/react';
import ChatSidebar from './ChatSidebar';

const active = [
  { id: 'a1', name: 'Сидорова Анна', initials: 'СА', role: 'Студент', lastMsg: 'Активный диалог', time: '', unread: 0 },
];
const system = { id: '__system__', system: true, name: 'Системные уведомления', initials: '', role: '', lastMsg: '', time: '', unread: 0 };
const archived = [
  { id: 'z1', name: 'Иванова Мария', initials: 'ИМ', role: 'Диалог закрыт', lastMsg: 'Диалог закрыт', time: '', unread: 0 },
  { id: 'z2', name: 'Петров Алексей', initials: 'ПА', role: 'Диалог закрыт', lastMsg: 'Диалог закрыт', time: '', unread: 3 },
];

function setup(props = {}) {
  const onSelect = jest.fn();
  render(
    <ChatSidebar
      contacts={[...active, system]}
      archivedContacts={props.archivedContacts ?? archived}
      activeId={null}
      onSelect={onSelect}
      {...props}
    />,
  );
  return { onSelect };
}

test('archive row shown with count when archived dialogs exist', () => {
  setup();
  const archiveBtn = screen.getByRole('button', { name: /Архив/ });
  expect(archiveBtn).toBeInTheDocument();
  expect(within(archiveBtn).getByText('2')).toBeInTheDocument(); // archived count (2 диалога)
});

test('archive collapsed by default — archived dialogs hidden', () => {
  setup();
  expect(screen.getByRole('button', { name: /Архив/ })).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByText('Иванова Мария')).not.toBeInTheDocument();
  // active + system всё равно видны
  expect(screen.getByText('Сидорова Анна')).toBeInTheDocument();
  expect(screen.getByText('Системные уведомления')).toBeInTheDocument();
});

test('clicking archive expands archived dialogs without selecting one', () => {
  const { onSelect } = setup();
  fireEvent.click(screen.getByRole('button', { name: /Архив/ }));
  expect(screen.getByText('Иванова Мария')).toBeInTheDocument();
  expect(screen.getByText('Петров Алексей')).toBeInTheDocument();
  expect(onSelect).not.toHaveBeenCalled(); // раскрытие не открывает диалог
});

test('no archive row when no archived dialogs', () => {
  setup({ archivedContacts: [] });
  expect(screen.queryByRole('button', { name: /Архив/ })).not.toBeInTheDocument();
});

test('archive row shows aggregated unread count', () => {
  setup();
  const archiveBtn = screen.getByRole('button', { name: /Архив/ });
  // суммарный unread архивных (0 + 3 = 3) отображается отдельным бейджем
  expect(within(archiveBtn).getByText('3')).toBeInTheDocument();
});
