import { fireEvent, render, screen, within } from '@testing-library/react';
import AuditEventsTable from './AuditEventsTable';
import AuthEventsTable from './AuthEventsTable';
import DataChangesTable from './DataChangesTable';

// ── Синтетические строки безопасного DTO ─────────────────────────────────────

const userActor = {
  kind: 'user',
  user_uuid: '11111111-1111-4111-8111-111111111111',
  display_name_current: 'Тестовый Пользователь',
  email_masked: 't***@example.test',
  role_at_event: 'admin',
  is_deleted_current: false,
};

const auditRow = (over = {}) => ({
  entry_id: '101',
  source: 'audit_log',
  occurred_at: '2026-08-22T11:03:07Z',
  event_code: 'admin_role_add',
  known_event: true,
  actor: userActor,
  target: {
    entity_type: 'user',
    entity_ref: null,
    user: {
      user_uuid: '22222222-2222-4222-8222-222222222222',
      display_name_current: 'Цель Действия',
      email_masked: 'c***@example.test',
      is_deleted_current: false,
    },
  },
  outcome: 'success',
  failure_code: null,
  details: {},
  details_redacted: false,
  ...over,
});

const authRow = (over = {}) => ({
  entry_id: '202',
  source: 'auth_log',
  occurred_at: '2026-08-22T11:03:07Z',
  event_code: 'login',
  known_event: true,
  actor: { ...userActor, role_at_event: null },
  success: true,
  failure_code: null,
  email_masked: 'l***@example.test',
  details_redacted: false,
  ...over,
});

const dclRow = (over = {}) => ({
  entry_id: '303',
  source: 'data_change_log',
  occurred_at: '2026-08-22T11:03:07Z',
  known_change: true,
  actor: userActor,
  table_name: 'meeting_types',
  record_id: 12,
  operation: 'UPDATE',
  changed_fields: ['duration_minutes', 'description'],
  target_user: null,
  details_redacted: false,
  ...over,
});

const TABLES = [
  ['AuditEventsTable', AuditEventsTable, auditRow],
  ['AuthEventsTable', AuthEventsTable, authRow],
  ['DataChangesTable', DataChangesTable, dclRow],
];

function renderTable(Table, props = {}) {
  const onOpenDetails = jest.fn();
  const onRetry = jest.fn();
  const view = render(
    <Table
      items={[]}
      loading={false}
      error={null}
      onRetry={onRetry}
      onOpenDetails={onOpenDetails}
      {...props}
    />,
  );
  return { onOpenDetails, onRetry, ...view };
}

describe.each(TABLES)('%s — общие состояния и разметка', (_name, Table, row) => {
  test('таблица доступна: caption, thead и th со scope="col"', () => {
    renderTable(Table, { items: [row()] });
    const table = screen.getByRole('table');
    expect(within(table).getByText(/Журнал/)).toBeInTheDocument();
    const headers = within(table).getAllByRole('columnheader');
    expect(headers.length).toBeGreaterThan(0);
    headers.forEach((th) => expect(th).toHaveAttribute('scope', 'col'));
  });

  test('загрузка показывает скелет вместо строк', () => {
    renderTable(Table, { items: [], loading: true });
    expect(screen.queryByText(/не найдено/)).toBeNull();
    expect(screen.getAllByRole('row').length).toBeGreaterThan(1);
  });

  test('ошибка показывается вместе с кнопкой «Повторить»', () => {
    const { onRetry } = renderTable(Table, { items: [], error: 'Журнал недоступен' });
    expect(screen.getByText('Журнал недоступен')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(onRetry).toHaveBeenCalled();
  });

  test('пустая выдача упоминает текущий период и фильтры', () => {
    renderTable(Table, { items: [] });
    expect(screen.getByText(/За выбранный период с текущими фильтрами/))
      .toBeInTheDocument();
  });

  test('строка не кликабельна целиком — только кнопка «Подробнее»', () => {
    const { onOpenDetails } = renderTable(Table, { items: [row()] });
    const dataRow = screen.getAllByRole('row')[1];
    fireEvent.click(dataRow);
    expect(onOpenDetails).not.toHaveBeenCalled();

    fireEvent.click(within(dataRow).getByRole('button', { name: /Подробнее/ }));
    expect(onOpenDetails).toHaveBeenCalledTimes(1);
  });

  test('кнопка «Подробнее» имеет содержательный aria-label', () => {
    renderTable(Table, { items: [row()] });
    const button = screen.getByRole('button', { name: /Подробнее/ });
    expect(button).toHaveAttribute('type', 'button');
    expect(button.getAttribute('aria-label')).toMatch(/22\.08\.2026, 14:03:07/);
  });

  test('время показано по Москве с секундами', () => {
    renderTable(Table, { items: [row()] });
    expect(screen.getByText('22.08.2026, 14:03:07')).toBeInTheDocument();
  });

  test('BIGINT entry_id не приводится к Number', () => {
    // 9007199254740993 = 2^53 + 1: Number(…) схлопнул бы его до 2^53.
    const big = '9007199254740993';
    const { container } = renderTable(Table, { items: [row({ entry_id: big })] });
    expect(container.innerHTML).not.toContain('9007199254740992');
    expect(Number(big).toString()).toBe('9007199254740992'); // контроль ловушки
  });
});

describe.each(TABLES)('%s — классы участника', (_name, Table, row) => {
  test('системный актор подписан «Система», без имени и email', () => {
    renderTable(Table, { items: [row({ actor: { kind: 'system' } })] });
    expect(screen.getByText('Система')).toBeInTheDocument();
    expect(screen.queryByText('Тестовый Пользователь')).toBeNull();
  });

  test('анонимный актор подписан отдельно', () => {
    renderTable(Table, { items: [row({ actor: { kind: 'anonymous' } })] });
    expect(screen.getByText('Анонимный пользователь')).toBeInTheDocument();
  });

  test('недоступный актор подписан как удалённый или недоступный', () => {
    renderTable(Table, { items: [row({ actor: { kind: 'unavailable' } })] });
    expect(screen.getByText('Удалённый или недоступный пользователь'))
      .toBeInTheDocument();
  });

  test('soft-deleted пользователь остаётся участником с пометкой', () => {
    renderTable(Table, {
      items: [row({ actor: { ...userActor, is_deleted_current: true } })],
    });
    expect(screen.getByText('Тестовый Пользователь')).toBeInTheDocument();
    expect(screen.getByText('Удалён')).toBeInTheDocument();
  });

  test('признак частичного сокрытия виден в строке', () => {
    renderTable(Table, { items: [row({ details_redacted: true })] });
    expect(screen.getByText('Часть данных скрыта')).toBeInTheDocument();
  });
});

describe('AuditEventsTable', () => {
  test('русская подпись события и роль действия из строки журнала', () => {
    renderTable(AuditEventsTable, { items: [auditRow()] });
    expect(screen.getByText('Администратор добавил роль')).toBeInTheDocument();
    expect(screen.getByText('Администратор')).toBeInTheDocument();
  });

  test('успех и отказ показаны разными badge', () => {
    const { unmount } = renderTable(AuditEventsTable, { items: [auditRow()] });
    expect(screen.getByText('Успешно')).toBeInTheDocument();
    unmount();

    renderTable(AuditEventsTable, {
      items: [auditRow({ outcome: 'failure', failure_code: 'access_denied' })],
    });
    expect(screen.getByText('Отказ')).toBeInTheDocument();
  });

  test('неизвестное событие получает нейтральную подпись, а не сырой код', () => {
    renderTable(AuditEventsTable, {
      items: [auditRow({
        event_code: 'legacy_unknown_event',
        known_event: false,
        outcome: null,
        target: null,
        details_redacted: true,
      })],
    });
    expect(screen.getByText('Неизвестное или историческое событие')).toBeInTheDocument();
    expect(screen.queryByText('legacy_unknown_event')).toBeNull();
  });

  test('цель-человек показана сводкой, внутренний id отсутствует', () => {
    const { container } = renderTable(AuditEventsTable, { items: [auditRow()] });
    expect(screen.getByText('Цель Действия')).toBeInTheDocument();
    expect(screen.getByText('c***@example.test')).toBeInTheDocument();
    expect(container.textContent).not.toContain('№');
  });

  test('цель-не-человек показана типом и номером', () => {
    renderTable(AuditEventsTable, {
      items: [auditRow({
        event_code: 'meeting_type_updated',
        target: { entity_type: 'meeting_type', entity_ref: 42, user: null },
      })],
    });
    expect(screen.getByText('Тип встречи')).toBeInTheDocument();
    expect(screen.getByText('№ 42')).toBeInTheDocument();
  });
});

describe('AuthEventsTable', () => {
  test('колонки роли нет — журнал её не хранит', () => {
    renderTable(AuthEventsTable, { items: [authRow()] });
    const headers = screen.getAllByRole('columnheader').map((th) => th.textContent);
    expect(headers).not.toContain('Роль действия');
    expect(headers).not.toContain('Роль');
  });

  test('неудачный вход показывает безопасную причину', () => {
    renderTable(AuthEventsTable, {
      items: [authRow({
        event_code: 'failed_login',
        success: false,
        failure_code: 'invalid_credentials',
        actor: { kind: 'anonymous' },
      })],
    });
    expect(screen.getByText('Неудачная попытка входа')).toBeInTheDocument();
    expect(screen.getByText('Отказ')).toBeInTheDocument();
    expect(screen.getByText('Неверные учётные данные')).toBeInTheDocument();
  });

  test('email в момент события показан маскированным', () => {
    renderTable(AuthEventsTable, { items: [authRow()] });
    expect(screen.getByText('l***@example.test')).toBeInTheDocument();
  });
});

describe('DataChangesTable', () => {
  test('имена изменённых полей переведены подписями своей таблицы', () => {
    renderTable(DataChangesTable, { items: [dclRow()] });
    expect(screen.getByText('Длительность, мин')).toBeInTheDocument();
    expect(screen.getByText('Описание типа встречи')).toBeInTheDocument();
  });

  test('одноимённое поле другой таблицы получает свою подпись', () => {
    renderTable(DataChangesTable, {
      items: [dclRow({
        table_name: 'group_sessions',
        changed_fields: ['description'],
      })],
    });
    expect(screen.getByText('Описание занятия')).toBeInTheDocument();
    expect(screen.queryByText('Описание типа встречи')).toBeNull();
  });

  test('для таблицы users вместо номера записи показана сводка пользователя', () => {
    renderTable(DataChangesTable, {
      items: [dclRow({
        table_name: 'users',
        record_id: null,
        changed_fields: ['full_name'],
        target_user: {
          user_uuid: '33333333-3333-4333-8333-333333333333',
          display_name_current: 'Изменённый Пользователь',
          email_masked: 'i***@example.test',
          is_deleted_current: false,
        },
      })],
    });
    expect(screen.getByText('Изменённый Пользователь')).toBeInTheDocument();
    expect(screen.getByText('ФИО')).toBeInTheDocument();
    expect(screen.queryByText(/№/)).toBeNull();
  });

  test('неизвестная таблица не роняет строку', () => {
    renderTable(DataChangesTable, {
      items: [dclRow({
        table_name: null,
        operation: null,
        changed_fields: [],
        details_redacted: true,
      })],
    });
    expect(screen.getByText('Часть данных скрыта')).toBeInTheDocument();
  });
});
