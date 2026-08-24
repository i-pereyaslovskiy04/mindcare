import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AuditLogsPage from './AuditLogsPage';
import {
  getAuditEvents, getAuditOptions, getAuthEvents, getDataChanges,
} from '../../../../api/audit.api';
import { getUsers } from '../../../../api/users.api';

jest.mock('../../../../api/audit.api', () => {
  const getAuditEventsMock = jest.fn();
  const getAuthEventsMock = jest.fn();
  const getDataChangesMock = jest.fn();
  return {
    getAuditOptions: jest.fn(),
    getAuditEvents: getAuditEventsMock,
    getAuthEvents: getAuthEventsMock,
    getDataChanges: getDataChangesMock,
    AUDIT_LOADERS: {
      audit_log: getAuditEventsMock,
      auth_log: getAuthEventsMock,
      data_change_log: getDataChangesMock,
    },
  };
});
jest.mock('../../../../api/users.api');

const OPTIONS = {
  audit_events: ['admin_role_add', 'article_created', 'audit_logs_viewed'],
  auth_events: ['login', 'failed_login'],
  actor_roles: ['admin', 'psychologist', 'student', 'supervisor'],
  outcomes: ['success', 'failure'],
  entity_types: ['appointment', 'user'],
  tables: ['meeting_types', 'users'],
  operations: ['UPDATE'],
  actor_kinds: {
    audit_log: ['user', 'system', 'unavailable'],
    auth_log: ['user', 'anonymous', 'unavailable'],
    data_change_log: ['user', 'unavailable'],
  },
  limits: {
    default_range_days: 7,
    max_range_days: 90,
    default_page_size: 20,
    max_page_size: 100,
    max_result_window: 100000,
    orders: ['asc', 'desc'],
  },
};

const page = (total = 0) => ({ items: [], total, page: 1, size: 20 });

beforeEach(() => {
  jest.clearAllMocks();
  getAuditOptions.mockResolvedValue(OPTIONS);
  getAuditEvents.mockResolvedValue(page(11));
  getAuthEvents.mockResolvedValue(page(22));
  getDataChanges.mockResolvedValue(page(33));
  getUsers.mockResolvedValue({ items: [], total: 0 });
});

async function renderPage() {
  const view = render(<AuditLogsPage />);
  await waitFor(() => expect(getAuditEvents).toHaveBeenCalled());
  // Ждём отрисовки таблицы: к этому моменту оба hook'а уже применили ответы.
  await screen.findByRole('table');
  return view;
}

describe('каркас страницы', () => {
  test('заголовок, пояснение и кнопка обновления', async () => {
    await renderPage();
    expect(screen.getByRole('heading', { name: 'Журнал действий' })).toBeInTheDocument();
    expect(screen.getByText(/Это не история каждого перехода по страницам/))
      .toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Обновить' })).toBeInTheDocument();
  });

  test('счётчик записей показан после загрузки', async () => {
    await renderPage();
    expect(await screen.findByText(/11 записей/)).toBeInTheDocument();
  });

  test('панель связана с активной вкладкой', async () => {
    await renderPage();
    const panel = screen.getByRole('tabpanel');
    const tab = screen.getByRole('tab', { name: 'Действия' });
    expect(panel).toHaveAttribute('aria-labelledby', tab.id);
    expect(tab).toHaveAttribute('aria-controls', panel.id);
  });
});

describe('вкладки бьют каждая в свой endpoint', () => {
  test('стартовая вкладка — только события audit_log', async () => {
    await renderPage();
    expect(getAuditEvents).toHaveBeenCalledTimes(1);
    expect(getAuthEvents).not.toHaveBeenCalled();
    expect(getDataChanges).not.toHaveBeenCalled();
  });

  test('переключение на «Входы и безопасность»', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Входы и безопасность' }));
    await waitFor(() => expect(getAuthEvents).toHaveBeenCalledTimes(1));
    expect(getDataChanges).not.toHaveBeenCalled();
    expect(await screen.findByText(/22 записей/)).toBeInTheDocument();
  });

  test('переключение на «Изменённые поля»', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Изменённые поля' }));
    await waitFor(() => expect(getDataChanges).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/33 записей/)).toBeInTheDocument();
  });

  test('клавиатурное переключение тоже меняет endpoint', async () => {
    await renderPage();
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'End' });
    await waitFor(() => expect(getDataChanges).toHaveBeenCalledTimes(1));
  });
});

describe('состав фильтров по вкладкам', () => {
  test('на «Действиях» есть категория, событие и объект', async () => {
    await renderPage();
    expect(screen.getByText('Категория событий')).toBeInTheDocument();
    expect(screen.getByText('Тип объекта')).toBeInTheDocument();
    expect(screen.getByLabelText('Идентификатор объекта')).toBeInTheDocument();
    expect(screen.getByText('Показывать просмотры журнала')).toBeInTheDocument();
  });

  test('на «Входах» нет фильтра роли — журнал её не хранит', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Входы и безопасность' }));
    await waitFor(() => expect(getAuthEvents).toHaveBeenCalled());
    expect(screen.queryByText('Роль действия')).toBeNull();
  });

  test('на «Изменённых полях» есть таблица, операция и идентификатор записи', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Изменённые поля' }));
    await waitFor(() => expect(getDataChanges).toHaveBeenCalled());
    expect(screen.getByText('Таблица')).toBeInTheDocument();
    // «Операция» есть и как подпись фильтра, и как заголовок колонки таблицы.
    expect(screen.getAllByText('Операция').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByLabelText('Идентификатор записи')).toBeInTheDocument();
  });

  test('идентификатор объекта заблокирован, пока не выбран тип', async () => {
    await renderPage();
    expect(screen.getByLabelText('Идентификатор объекта')).toBeDisabled();
    expect(screen.getByText(/Доступен после выбора типа объекта/)).toBeInTheDocument();
  });

  test('период показан текстом', async () => {
    await renderPage();
    expect(screen.getByText(/^Период: \d{2}\.\d{2}\.\d{4} — \d{2}\.\d{2}\.\d{4}$/))
      .toBeInTheDocument();
  });
});

describe('ошибка справочника отделена от ошибки списка', () => {
  test('журнал остаётся рабочим, registry-селекты гаснут', async () => {
    getAuditOptions.mockRejectedValueOnce(new Error('Справочник недоступен'));
    await renderPage();

    expect(await screen.findByText(/Справочник фильтров недоступен/))
      .toBeInTheDocument();

    // Список всё равно загружен.
    expect(getAuditEvents).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('table')).toBeInTheDocument();

    // Registry-зависимый селект отключён, базовые фильтры доступны.
    expect(screen.getByRole('button', { name: /Категория событий/ })).toBeDisabled();
    expect(screen.getByLabelText('Участник')).toBeEnabled();
  });

  test('есть отдельная кнопка повторной загрузки справочника', async () => {
    getAuditOptions.mockRejectedValueOnce(new Error('Справочник недоступен'));
    await renderPage();

    const retry = await screen.findByRole('button', {
      name: 'Загрузить справочник заново',
    });
    getAuditOptions.mockResolvedValueOnce(OPTIONS);
    fireEvent.click(retry);

    await waitFor(() => expect(getAuditOptions).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.queryByText(/Справочник фильтров недоступен/)).toBeNull());
  });

  test('ошибка справочника не подменяет ошибку списка', async () => {
    getAuditOptions.mockRejectedValueOnce(new Error('Справочник недоступен'));
    getAuditEvents.mockRejectedValueOnce(new Error('Журнал недоступен'));
    await renderPage();

    expect(await screen.findByText('Журнал недоступен')).toBeInTheDocument();
    expect(screen.getByText(/Справочник фильтров недоступен/)).toBeInTheDocument();
    // Две разные ошибки в двух разных местах, а не одна вместо другой.
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
  });

  test('ошибка списка не мешает пользоваться фильтрами', async () => {
    getAuditEvents.mockRejectedValueOnce(new Error('Журнал недоступен'));
    await renderPage();

    expect(await screen.findByText('Журнал недоступен')).toBeInTheDocument();
    expect(screen.getByLabelText('Участник')).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Сбросить фильтры' })).toBeEnabled();
  });
});

describe('обновление и сброс', () => {
  test('«Обновить» перезапрашивает текущий журнал', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Обновить' }));
    await waitFor(() => expect(getAuditEvents).toHaveBeenCalledTimes(2));
  });

  test('«Сбросить фильтры» доступен и перезапрашивает', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Сбросить фильтры' }));
    await waitFor(() => expect(getAuditEvents).toHaveBeenCalledTimes(2));
  });
});

describe('пагинация', () => {
  test('при одной странице пагинации нет', async () => {
    await renderPage();
    expect(screen.queryByText(/Стр\. /)).toBeNull();
  });

  test('при нескольких страницах видны кнопки', async () => {
    getAuditEvents.mockResolvedValue(page(120));
    await renderPage();
    expect(await screen.findByText('Стр. 1 из 6')).toBeInTheDocument();
  });
});
