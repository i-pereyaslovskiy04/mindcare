import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AuditDetailsModal from './AuditDetailsModal';
import { apiFetch } from '../../../../api/client';

jest.mock('../../../../api/client');

const ACTOR = {
  kind: 'user',
  user_uuid: '11111111-1111-4111-8111-111111111111',
  display_name_current: 'Тестовый Пользователь',
  email_masked: 't***@example.test',
  role_at_event: 'admin',
  is_deleted_current: false,
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
    },
  },
  outcome: 'success',
  failure_code: null,
  details: {
    roles_before: ['student'],
    roles_after: ['student', 'psychologist'],
    added: ['psychologist'],
  },
  details_redacted: false,
};

beforeEach(() => {
  jest.clearAllMocks();
});

function openModal(item = AUDIT_ITEM) {
  const onClose = jest.fn();
  const view = render(<AuditDetailsModal item={item} onClose={onClose} />);
  return { onClose, ...view };
}

describe('открытие и закрытие', () => {
  test('без item модалка ничего не показывает', () => {
    render(<AuditDetailsModal item={null} onClose={jest.fn()} />);
    expect(screen.queryByText('Запись журнала')).toBeNull();
  });

  test('с item показывает диалог', () => {
    openModal();
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByText('Запись журнала')).toBeInTheDocument();
  });

  test('Escape закрывает', () => {
    const { onClose } = openModal();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  test('кнопка закрытия вызывает onClose', () => {
    const { onClose } = openModal();
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    expect(onClose).toHaveBeenCalled();
  });

  test('фокус уходит внутрь диалога', async () => {
    openModal();
    // Modal переводит фокус на первый интерактивный элемент карточки.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Закрыть' })).toHaveFocus());
  });

  test('фокус возвращается на элемент, открывший модалку', async () => {
    function Harness({ item }) {
      return (
        <>
          <button type="button">Подробнее</button>
          <AuditDetailsModal item={item} onClose={jest.fn()} />
        </>
      );
    }

    const { rerender } = render(<Harness item={null} />);
    const trigger = screen.getByRole('button', { name: 'Подробнее' });
    trigger.focus();

    rerender(<Harness item={AUDIT_ITEM} />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Закрыть' })).toHaveFocus());

    rerender(<Harness item={null} />);
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});

describe('модалка не ходит в сеть', () => {
  test('открытие не выполняет ни одного запроса', () => {
    openModal();
    expect(apiFetch).not.toHaveBeenCalled();
  });
});

describe('только разрешённые поля', () => {
  test('время с явной подписью пояса', () => {
    openModal();
    expect(screen.getByText('22.08.2026, 14:03:07 МСК')).toBeInTheDocument();
  });

  test('участник, его текущие данные и роль действия', () => {
    openModal();
    expect(screen.getByText('Текущее ФИО')).toBeInTheDocument();
    expect(screen.getByText('Тестовый Пользователь')).toBeInTheDocument();
    expect(screen.getByText('t***@example.test')).toBeInTheDocument();
    expect(screen.getByText('Роль действия')).toBeInTheDocument();
  });

  test('событие показано подписью и стабильным кодом', () => {
    openModal();
    expect(screen.getByText('Администратор добавил роль')).toBeInTheDocument();
    expect(screen.getByText('admin_role_add')).toBeInTheDocument();
  });

  test('разрешённые ключи details переведены подписями', () => {
    openModal();
    expect(screen.getByText('Роли до')).toBeInTheDocument();
    expect(screen.getByText('Студент')).toBeInTheDocument();
    expect(screen.getByText('Роли после')).toBeInTheDocument();
    expect(screen.getByText('Студент, Психолог')).toBeInTheDocument();
    expect(screen.getByText('Добавлено')).toBeInTheDocument();
  });

  test('неизвестный ключ details не отрисовывается', () => {
    const { container } = openModal({
      ...AUDIT_ITEM,
      details: {
        ...AUDIT_ITEM.details,
        secret_internal_key: 'СЕКРЕТНОЕ_ЗНАЧЕНИЕ',
        linked_user_id: 4242,
      },
    });
    expect(container.textContent).not.toContain('СЕКРЕТНОЕ_ЗНАЧЕНИЕ');
    expect(container.textContent).not.toContain('secret_internal_key');
    expect(container.textContent).not.toContain('4242');
  });

  test('linked_user_uuid отдаётся как UUID, без внутреннего id', () => {
    openModal({
      ...AUDIT_ITEM,
      event_code: 'unregistered_student_card_linked',
      details: { linked_user_uuid: '44444444-4444-4444-8444-444444444444' },
    });
    expect(screen.getByText('Привязанный пользователь')).toBeInTheDocument();
    expect(screen.getByText('44444444-4444-4444-8444-444444444444')).toBeInTheDocument();
  });

  test('размер вложения форматируется, MIME показан кодом', () => {
    openModal({
      ...AUDIT_ITEM,
      event_code: 'chat_attachment_uploaded',
      details: { file_size: 2048, mime_type: 'application/pdf' },
    });
    expect(screen.getByText('2 КБ')).toBeInTheDocument();
    expect(screen.getByText('application/pdf')).toBeInTheDocument();
  });
});

describe('маркер сокрытия', () => {
  test('при details_redacted показано нейтральное сообщение', () => {
    openModal({ ...AUDIT_ITEM, details_redacted: true });
    expect(screen.getByText('Часть исторических данных скрыта политикой безопасности.'))
      .toBeInTheDocument();
  });

  test('без сокрытия сообщения нет', () => {
    openModal();
    expect(screen.queryByText(/скрыта политикой безопасности/)).toBeNull();
  });

  test('неизвестное событие подписано нейтрально', () => {
    openModal({
      ...AUDIT_ITEM,
      event_code: 'legacy_unknown_event',
      known_event: false,
      outcome: null,
      target: null,
      details: {},
      details_redacted: true,
    });
    expect(screen.getByText('Неизвестное или историческое событие')).toBeInTheDocument();
  });
});

describe('строки других журналов', () => {
  test('auth_log: результат, причина отказа и email момента события', () => {
    openModal({
      entry_id: '202',
      source: 'auth_log',
      occurred_at: '2026-08-22T11:03:07Z',
      event_code: 'failed_login',
      known_event: true,
      actor: { kind: 'anonymous' },
      success: false,
      failure_code: 'invalid_credentials',
      email_masked: 'l***@example.test',
      details_redacted: false,
    });

    expect(screen.getByText('Неудачная попытка входа')).toBeInTheDocument();
    expect(screen.getByText('Отказ')).toBeInTheDocument();
    expect(screen.getByText('Неверные учётные данные')).toBeInTheDocument();
    expect(screen.getByText('l***@example.test')).toBeInTheDocument();
    // Роль в этом журнале не хранится и не подставляется.
    expect(screen.queryByText('Роль действия')).toBeNull();
  });

  test('data_change_log: операция, таблица и имена полей', () => {
    openModal({
      entry_id: '303',
      source: 'data_change_log',
      occurred_at: '2026-08-22T11:03:07Z',
      known_change: true,
      actor: ACTOR,
      table_name: 'meeting_types',
      record_id: 12,
      operation: 'UPDATE',
      changed_fields: ['duration_minutes'],
      target_user: null,
      details: {},
      details_redacted: false,
    });

    expect(screen.getByText('Изменение')).toBeInTheDocument();
    expect(screen.getByText('Типы встреч')).toBeInTheDocument();
    expect(screen.getByText('№ 12')).toBeInTheDocument();
    expect(screen.getByText('Длительность, мин')).toBeInTheDocument();
  });

  test('audit_logs_viewed: журнал и применённые фильтры читаемы', () => {
    openModal({
      ...AUDIT_ITEM,
      event_code: 'audit_logs_viewed',
      target: null,
      details: { journal: 'auth_log', filter_keys: ['date_range', 'success'] },
    });

    expect(screen.getByText('Просмотр журнала аудита')).toBeInTheDocument();
    expect(screen.getByText('Входы и безопасность')).toBeInTheDocument();
    expect(screen.getByText('период, результат входа')).toBeInTheDocument();
  });
});
