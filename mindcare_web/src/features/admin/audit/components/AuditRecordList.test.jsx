import fs from 'fs';
import path from 'path';
import { fireEvent, render, screen, within } from '@testing-library/react';
import AuditEventsTable from './AuditEventsTable';
import AuthEventsTable from './AuthEventsTable';
import DataChangesTable from './DataChangesTable';

// Узкое представление журналов (< 56rem): хронологический список. jsdom не
// применяет CSS — таблица и список оба в DOM; здесь проверяется список.

const userActor = {
  kind: 'user',
  user_uuid: '11111111-1111-4111-8111-111111111111',
  display_name_current: 'Тестовый Пользователь',
  email_masked: 't***@example.test',
  role_at_event: 'admin',
  is_deleted_current: false,
};

const auditRow = (over = {}) => ({
  entry_id: '101', source: 'audit_log', occurred_at: '2026-08-22T11:03:07Z',
  event_code: 'admin_role_add', known_event: true, actor: userActor,
  target: {
    entity_type: 'user', entity_ref: null,
    user: { user_uuid: '22222222-2222-4222-8222-222222222222', display_name_current: 'Цель Действия', email_masked: 'c***@example.test', is_deleted_current: false },
  },
  outcome: 'success', failure_code: null, details: {}, details_redacted: false, ...over,
});

const authRow = (over = {}) => ({
  entry_id: '202', source: 'auth_log', occurred_at: '2026-08-22T11:03:07Z',
  event_code: 'login', known_event: true, actor: { ...userActor, role_at_event: null },
  success: true, failure_code: null, email_masked: null, auth_method: 'yandex', details_redacted: false, ...over,
});

const dclRow = (over = {}) => ({
  entry_id: '303', source: 'data_change_log', occurred_at: '2026-08-22T11:03:07Z',
  known_change: true, actor: userActor, table_name: 'meeting_types', record_id: 12,
  operation: 'UPDATE', changed_fields: ['duration_minutes', 'description'], target_user: null,
  details_redacted: false, ...over,
});

function showLog(Table, items, onOpenDetails = jest.fn()) {
  render(
    <Table items={items} loading={false} error={null} onRetry={jest.fn()} onOpenDetails={onOpenDetails} />,
  );
  return onOpenDetails;
}

const list = (name) => screen.getByRole('list', { name });
const records = (name) => within(list(name)).getAllByRole('listitem');

describe('общая модель записи', () => {
  test('ul/li; заголовок записи (h2) — время и событие; строка не кликабельна, только «Подробнее»', () => {
    const item = auditRow();
    const onOpen = showLog(AuditEventsTable, [item]);
    const [record] = records('Журнал действий');
    const heading = within(record).getByRole('heading', { level: 2 });
    expect(heading).toHaveTextContent('22.08.2026, 14:03:07');
    expect(heading).toHaveTextContent('Администратор добавил роль');

    fireEvent.click(record);
    expect(onOpen).not.toHaveBeenCalled();
    const details = within(record).getByRole('button', { name: /^Подробнее о событии «Администратор добавил роль» от 22\.08\.2026, 14:03:07$/ });
    expect(details).toHaveTextContent('Подробнее');
    fireEvent.click(details);
    expect(onOpen).toHaveBeenCalledWith(item);
  });

  test('ошибка и пустая выдача — один раз, без таблицы и списка', () => {
    const { rerender } = render(
      <AuditEventsTable items={[]} loading={false} error="Журнал недоступен" onRetry={jest.fn()} onOpenDetails={jest.fn()} />,
    );
    expect(screen.getAllByText('Журнал недоступен')).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Повторить' })).toHaveLength(1);
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByRole('list')).toBeNull();

    rerender(<AuditEventsTable items={[]} loading={false} error={null} onRetry={jest.fn()} onOpenDetails={jest.fn()} />);
    expect(screen.getAllByText(/За выбранный период с текущими фильтрами/)).toHaveLength(1);
  });

  test('загрузка — скелет и в таблице, и в списке (aria-busy)', () => {
    render(<AuditEventsTable items={[]} loading error={null} onRetry={jest.fn()} onOpenDetails={jest.fn()} />);
    expect(list('Журнал действий')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getAllByRole('row').length).toBeGreaterThan(1);
  });
});

describe('Действия (audit_log)', () => {
  test('участник → объект, результат и роль действия', () => {
    showLog(AuditEventsTable, [auditRow({ outcome: 'failure', failure_code: 'access_denied' })]);
    const [record] = records('Журнал действий');
    expect(within(record).getByText('Участник')).toBeInTheDocument();
    expect(within(record).getByText('Тестовый Пользователь')).toBeInTheDocument();
    expect(within(record).getByText('Объект')).toBeInTheDocument();
    expect(within(record).getByText('Цель Действия')).toBeInTheDocument();
    expect(within(record).getByText('Отказ')).toBeInTheDocument();
    expect(within(record).getByRole('term')).toHaveTextContent('Роль действия');
    expect(within(record).getByRole('definition')).toHaveTextContent('Администратор');
  });

  test('системный, недоступный и удалённый участник; отметка скрытых данных', () => {
    showLog(AuditEventsTable, [
      auditRow({ entry_id: '1', actor: { kind: 'system' }, target: null, outcome: null }),
      auditRow({ entry_id: '2', actor: { kind: 'unavailable' }, details_redacted: true }),
      auditRow({ entry_id: '3', actor: { ...userActor, is_deleted_current: true } }),
    ]);
    const [sys, gone, deleted] = records('Журнал действий');
    expect(within(sys).getByText('Система')).toBeInTheDocument();
    expect(within(sys).queryByText('Объект')).toBeNull();
    expect(within(sys).queryByText(/Успешно|Отказ/)).toBeNull();
    expect(within(gone).getByText('Удалённый или недоступный пользователь')).toBeInTheDocument();
    expect(within(gone).getByText('Часть данных скрыта')).toBeInTheDocument();
    expect(within(deleted).getByText('Удалён')).toBeInTheDocument();
  });
});

describe('Входы и безопасность (auth_log)', () => {
  test('объекта нет; способ входа и безопасная причина отказа — в деталях', () => {
    showLog(AuthEventsTable, [authRow({
      event_code: 'failed_login', success: false, failure_code: 'account_disabled',
      auth_method: 'password', actor: { kind: 'anonymous' }, email_masked: 'k*****@example.test',
    })]);
    const [record] = records('Журнал входов и безопасности');
    expect(within(record).getByText('Пользователь')).toBeInTheDocument();
    expect(within(record).queryByText('Объект')).toBeNull();
    expect(within(record).getByText('Отказ')).toBeInTheDocument();
    expect(within(record).getAllByRole('term').map((t) => t.textContent)).toEqual(['Способ входа', 'Причина']);
    expect(within(record).getByText('Учётная запись отключена')).toBeInTheDocument();
  });

  test('анонимный участник и email события — отдельные элементы с подписью, не склеены', () => {
    showLog(AuthEventsTable, [authRow({ actor: { kind: 'anonymous' }, email_masked: 'k*****@example.test' })]);
    const table = screen.getByRole('table');
    const kind = within(table).getByText('Анонимный пользователь');
    const email = within(table).getByText('k*****@example.test', { exact: false });
    expect(kind).not.toContainElement(email);
    // eslint-disable-next-line testing-library/no-node-access
    expect(kind.closest('div')).not.toContainElement(email);
    expect(email).toHaveTextContent('Email события: k*****@example.test');
  });

  test('текущий email и email события подписаны, когда показаны оба', () => {
    showLog(AuthEventsTable, [authRow({ email_masked: 'l***@example.test' })]);
    const [record] = records('Журнал входов и безопасности');
    expect(within(record).getByText('t***@example.test', { exact: false }))
      .toHaveTextContent('Email сейчас: t***@example.test');
    expect(within(record).getByText('l***@example.test', { exact: false }))
      .toHaveTextContent('Email события: l***@example.test');
  });

  test('без email события текущий email без подписи', () => {
    showLog(AuthEventsTable, [authRow({ email_masked: null })]);
    const [record] = records('Журнал входов и безопасности');
    expect(within(record).getByText('t***@example.test')).toBeInTheDocument();
    expect(within(record).queryByText(/Email сейчас|Email события/)).toBeNull();
  });
});

describe('Изменённые поля (data_change_log)', () => {
  test('операция — заголовок; участник → таблица и запись', () => {
    showLog(DataChangesTable, [dclRow()]);
    const [record] = records('Журнал изменённых полей');
    expect(within(record).getByRole('heading', { level: 2 })).toHaveTextContent('Изменение');
    expect(within(record).getByText('Таблица и запись')).toBeInTheDocument();
    expect(within(record).getByText('№ 12')).toBeInTheDocument();
  });

  test('поля: 0 — строки нет; 1 — без «+K»; много — первые 3 и «+K»', () => {
    showLog(DataChangesTable, [
      dclRow({ entry_id: '1', changed_fields: [] }),
      dclRow({ entry_id: '2', changed_fields: ['duration_minutes'] }),
      dclRow({ entry_id: '3', changed_fields: ['name', 'description', 'duration_minutes', 'buffer_minutes', 'is_active'] }),
    ]);
    const [none, one, many] = records('Журнал изменённых полей');
    expect(within(none).queryByText(/Изменено полей/)).toBeNull();
    expect(within(one).getByText('Изменено полей: 1')).toBeInTheDocument();
    expect(within(one).queryByText(/^\+\d/)).toBeNull();
    expect(within(many).getByText('Изменено полей: 5')).toBeInTheDocument();
    expect(within(many).getByText('+2')).toBeInTheDocument();
    // В таблице — полный список.
    const lastRow = within(screen.getByRole('table')).getAllByRole('row').at(-1);
    expect(within(lastRow).queryByText('+2')).toBeNull();
  });
});

describe('контракт адаптивного слоя', () => {
  const read = (file) => fs.readFileSync(path.join(__dirname, file), 'utf8');

  test('границы 56rem / 39rem — только в слое Audit, у таблицы своих нет', () => {
    expect(read('AuditLogView.module.css')).toMatch(/container-type:\s*inline-size/);
    expect(read('AuditLogView.module.css')).toMatch(/@container \(min-width: 56rem\)/);
    expect(read('AuditRecordList.module.css')).toMatch(/@container \(min-width: 39rem\)/);
    expect(read('AuditFilters.module.css')).toMatch(/@container \(min-width: 56rem\)/);
    const shell = read('AuditTableShell.module.css');
    expect(shell).not.toMatch(/@container|@media/);
    expect(shell).not.toMatch(/min-width:\s*\d{3}px/);
    const page = fs.readFileSync(path.join(__dirname, '..', 'pages', 'AuditLogsPage.module.css'), 'utf8');
    expect(page).not.toMatch(/@container|@media/);
  });

  test('журналы — конфигурации одного слоя, без своей разметки таблицы и shared ResponsiveTable', () => {
    ['AuditEventsTable.jsx', 'AuthEventsTable.jsx', 'DataChangesTable.jsx'].forEach((file) => {
      const src = read(file);
      expect(src).toMatch(/AuditLogView/);
      expect(src).not.toMatch(/<table|<tr|ResponsiveTable/);
    });
  });

  test('заголовок колонки «Подробнее» — обычный th с visually-hidden текстом', () => {
    showLog(AuditEventsTable, [auditRow()]);
    const headers = within(screen.getByRole('table')).getAllByRole('columnheader');
    const last = headers.at(-1);
    expect(last).toHaveTextContent('Подробнее');
    // eslint-disable-next-line testing-library/no-node-access
    expect(last.querySelector('.visually-hidden')).not.toBeNull();
    expect(read('AuditTableShell.module.css')).not.toMatch(/srOnlyHead/);
  });
});
