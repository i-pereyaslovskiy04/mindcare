import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import AuditDetailsModal from './AuditDetailsModal';
import AuditEventsTable from './AuditEventsTable';
import AuthEventsTable from './AuthEventsTable';
import DataChangesTable from './DataChangesTable';

/**
 * Контроль утечек рендеринга.
 *
 * Backend уже гарантирует отсутствие этих полей структурно — их нет в схемах
 * DTO. Тест закрывает вторую половину контракта: если такое поле всё же придёт
 * (изменение backend, прокси, мок в разработке), компоненты обязаны его
 * проигнорировать, а не показать. Все значения синтетические.
 */

const CANARIES = {
  full_email: 'polnyy.adres@example.test',
  ip_address: '203.0.113.77',
  user_agent: 'Mozilla/5.0 (КАНАРЕЙКА UA)',
  session_id: 'sess-КАНАРЕЙКА-0123456789abcdef',
  request_url: 'https://example.test/api/admin/КАНАРЕЙКА',
  request_method: 'DELETE',
  description: 'Свободное описание КАНАРЕЙКА',
  metadata: { raw_key: 'СЫРАЯ_МЕТАДАТА_КАНАРЕЙКА' },
  password: 'p@ssw0rd-КАНАРЕЙКА',
  token: 'tok_КАНАРЕЙКА_abcdef',
  traceback: 'Traceback (most recent call last): КАНАРЕЙКА',
  sql: 'SELECT * FROM users WHERE id = 1 -- КАНАРЕЙКА',
  old_values: { full_name: 'Старое ФИО КАНАРЕЙКА' },
  new_values: { full_name: 'Новое ФИО КАНАРЕЙКА' },
  content: 'Расшифрованный текст заметки КАНАРЕЙКА',
  mfa_method: 'totp-КАНАРЕЙКА',
  failure_reason: 'Полный текст исключения КАНАРЕЙКА',
};

/** Строки, которых не должно быть в DOM ни при каких обстоятельствах. */
const FORBIDDEN_STRINGS = [
  'polnyy.adres@example.test',
  '203.0.113.77',
  'Mozilla/5.0',
  'sess-КАНАРЕЙКА',
  'https://example.test/api/admin/КАНАРЕЙКА',
  'Свободное описание',
  'СЫРАЯ_МЕТАДАТА_КАНАРЕЙКА',
  'p@ssw0rd',
  'tok_КАНАРЕЙКА',
  'Traceback',
  'SELECT * FROM users',
  'Старое ФИО',
  'Новое ФИО',
  'Расшифрованный текст заметки',
  'totp-КАНАРЕЙКА',
  'Полный текст исключения',
  'КАНАРЕЙКА',
];

const ACTOR = {
  kind: 'user',
  user_uuid: '11111111-1111-4111-8111-111111111111',
  display_name_current: 'Тестовый Пользователь',
  email_masked: 't***@example.test',
  role_at_event: 'admin',
  is_deleted_current: false,
  // Лишние поля прямо внутри actor.
  ...CANARIES,
};

const AUDIT_ITEM = {
  entry_id: '101',
  source: 'audit_log',
  occurred_at: '2026-08-22T11:03:07Z',
  event_code: 'admin_role_add',
  known_event: true,
  actor: ACTOR,
  target: {
    entity_type: 'user',
    entity_ref: null,
    user: {
      user_uuid: '22222222-2222-4222-8222-222222222222',
      display_name_current: 'Цель Действия',
      email_masked: 'c***@example.test',
      is_deleted_current: false,
      ...CANARIES,
    },
    ...CANARIES,
  },
  outcome: 'success',
  failure_code: null,
  details: { roles_after: ['student'], ...CANARIES },
  details_redacted: false,
  ...CANARIES,
};

const AUTH_ITEM = {
  entry_id: '202',
  source: 'auth_log',
  occurred_at: '2026-08-22T11:03:07Z',
  event_code: 'login',
  known_event: true,
  actor: ACTOR,
  success: true,
  failure_code: null,
  email_masked: 'l***@example.test',
  details_redacted: false,
  ...CANARIES,
};

const DCL_ITEM = {
  entry_id: '303',
  source: 'data_change_log',
  occurred_at: '2026-08-22T11:03:07Z',
  known_change: true,
  actor: ACTOR,
  table_name: 'users',
  record_id: null,
  operation: 'UPDATE',
  changed_fields: ['full_name'],
  target_user: {
    user_uuid: '33333333-3333-4333-8333-333333333333',
    display_name_current: 'Изменённый Пользователь',
    email_masked: 'i***@example.test',
    is_deleted_current: false,
    ...CANARIES,
  },
  details: CANARIES,
  details_redacted: false,
  ...CANARIES,
};

function expectNoLeak(container) {
  const html = container.innerHTML;
  const text = container.textContent;
  FORBIDDEN_STRINGS.forEach((needle) => {
    expect(html).not.toContain(needle);
    expect(text).not.toContain(needle);
  });
}

describe('таблицы игнорируют неожиданные поля ответа', () => {
  test.each([
    ['AuditEventsTable', AuditEventsTable, AUDIT_ITEM],
    ['AuthEventsTable', AuthEventsTable, AUTH_ITEM],
    ['DataChangesTable', DataChangesTable, DCL_ITEM],
  ])('%s не показывает ни одного контрольного значения', (_name, Table, item) => {
    const { container } = render(
      <Table
        items={[item]}
        loading={false}
        error={null}
        onRetry={jest.fn()}
        onOpenDetails={jest.fn()}
      />,
    );

    // Легитимные поля на месте — проверка не «пустая».
    expect(screen.getByText('Тестовый Пользователь')).toBeInTheDocument();
    expectNoLeak(container);
  });
});

describe('модалка игнорирует неожиданные поля ответа', () => {
  test.each([
    ['audit_log', AUDIT_ITEM],
    ['auth_log', AUTH_ITEM],
    ['data_change_log', DCL_ITEM],
  ])('строка %s не протекает в подробностях', (_name, item) => {
    const { baseElement } = render(
      <AuditDetailsModal item={item} onClose={jest.fn()} />,
    );

    expect(screen.getByText('Запись журнала')).toBeInTheDocument();
    expectNoLeak(baseElement);
  });
});

describe('сквозной путь таблица → модалка', () => {
  test('открытие подробностей из строки не показывает лишних полей', () => {
    function Harness() {
      const [item, setItem] = useState(null);
      return (
        <>
          <AuditEventsTable
            items={[AUDIT_ITEM]}
            loading={false}
            error={null}
            onRetry={jest.fn()}
            onOpenDetails={setItem}
          />
          <AuditDetailsModal item={item} onClose={() => setItem(null)} />
        </>
      );
    }

    const { baseElement } = render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: /Подробнее/ }));

    expect(screen.getByText('Запись журнала')).toBeInTheDocument();
    expectNoLeak(baseElement);
  });
});

describe('маскированный email не разворачивается', () => {
  test('в DOM попадает только маска, но не полный адрес', () => {
    const { container } = render(
      <AuditEventsTable
        items={[AUDIT_ITEM]}
        loading={false}
        error={null}
        onRetry={jest.fn()}
        onOpenDetails={jest.fn()}
      />,
    );
    expect(container.textContent).toContain('t***@example.test');
    expect(container.textContent).not.toContain('polnyy.adres');
  });
});
