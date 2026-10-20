import { act, renderHook, waitFor } from '@testing-library/react';
import useMyContacts from './useMyContacts';
import { getMyContacts, saveMyContacts } from '../../../api/contacts.api';

jest.mock('../../../api/contacts.api');

const CATALOG = {
  types: [
    { code: 'phone', label: 'Телефон', service_kind: null },
    { code: 'email', label: 'Email', service_kind: null },
    { code: 'messenger', label: 'Мессенджер', service_kind: 'messenger' },
  ],
  services: { messenger: [{ code: 'telegram', label: 'Telegram' }] },
};
const LIMITS = { max_items: 3, label_max: 80, value_max: 500 };
const ITEM = { id: 'id-1', type: 'phone', service: null, value: '+79001234567', label: null };

const snapshot = (over = {}) => ({
  version: 1, updated_at: null, items: [ITEM], limits: LIMITS, catalog: CATALOG, ...over,
});

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const apiError = (status, code, body = {}) => Object.assign(new Error('boom'), { status, code, body });

async function ready(initial = snapshot()) {
  getMyContacts.mockResolvedValue(initial);
  const view = renderHook(() => useMyContacts({ enabled: true }));
  await waitFor(() => expect(view.result.current.status).toBe('ready'));
  return view;
}

describe('useMyContacts', () => {
  it('enabled=false — запросов нет', () => {
    const { result } = renderHook(() => useMyContacts({ enabled: false }));
    expect(result.current.status).toBe('idle');
    expect(getMyContacts).not.toHaveBeenCalled();
  });

  it('загружает контакты и строит черновик', async () => {
    const { result } = await ready();
    expect(result.current.rows).toHaveLength(1);
    expect(result.current.dirty).toBe(false);
    expect(result.current.canAdd).toBe(true);
  });

  it('ошибка загрузки → loadError и повтор', async () => {
    getMyContacts.mockRejectedValueOnce(new Error('нет сети'));
    const { result } = renderHook(() => useMyContacts({ enabled: true }));
    await waitFor(() => expect(result.current.status).toBe('loadError'));
    expect(result.current.loadError).toBe('нет сети');
    getMyContacts.mockResolvedValueOnce(snapshot());
    await act(async () => { await result.current.retryLoad(); });
    expect(result.current.status).toBe('ready');
  });

  it('устаревший ответ загрузки отбрасывается', async () => {
    const first = deferred();
    const second = deferred();
    getMyContacts.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { result } = renderHook(() => useMyContacts({ enabled: true }));
    act(() => { result.current.retryLoad(); });
    await act(async () => { second.resolve(snapshot({ version: 5 })); });
    await act(async () => { first.resolve(snapshot({ version: 2 })); });
    await waitFor(() => expect(result.current.version).toBe(5));
  });

  it('добавление строки ограничено лимитом', async () => {
    const { result } = await ready();
    act(() => { result.current.addRow(); });
    act(() => { result.current.addRow(); });
    act(() => { result.current.addRow(); });
    expect(result.current.rows).toHaveLength(3);
    expect(result.current.canAdd).toBe(false);
  });

  it('смена типа сбрасывает сервис', async () => {
    const { result } = await ready();
    act(() => { result.current.updateRow('id-1', { type: 'messenger' }); });
    act(() => { result.current.updateRow('id-1', { service: 'telegram' }); });
    act(() => { result.current.updateRow('id-1', { type: 'email' }); });
    expect(result.current.rows[0].service).toBe('');
  });

  it('невалидный черновик не отправляется, фокус на первое ошибочное поле', async () => {
    const { result } = await ready();
    act(() => { result.current.updateRow('id-1', { value: 'abc' }); });
    await act(async () => { await result.current.save(); });
    expect(saveMyContacts).not.toHaveBeenCalled();
    expect(result.current.saveState).toBe('error');
    expect(result.current.fieldErrors['id-1'].value).toBeTruthy();
    expect(result.current.focusTarget).toMatchObject({ id: 'id-1', field: 'value' });
  });

  it('сохранение отправляет версию и payload, затем принимает ответ сервера', async () => {
    const { result } = await ready();
    act(() => { result.current.updateRow('id-1', { value: '+79001112233' }); });
    saveMyContacts.mockResolvedValue(snapshot({
      version: 2, changed: true, items: [{ ...ITEM, value: '+79001112233' }],
    }));
    await act(async () => { await result.current.save(); });
    expect(saveMyContacts).toHaveBeenCalledWith({
      version: 1,
      items: [{ id: 'id-1', type: 'phone', service: null, value: '+79001112233', label: null }],
    });
    expect(result.current.saveState).toBe('saved');
    expect(result.current.version).toBe(2);
    expect(result.current.dirty).toBe(false);
  });

  it('ошибка сохранения не стирает введённое; повтор несёт те же id', async () => {
    const { result } = await ready();
    act(() => { result.current.addRow('email'); });
    const newId = result.current.rows[1].id;
    act(() => { result.current.updateRow(newId, { value: 'me@example.org' }); });
    saveMyContacts.mockRejectedValueOnce(new Error('сеть пропала'));
    await act(async () => { await result.current.save(); });
    expect(result.current.saveState).toBe('error');
    expect(result.current.rows[1].value).toBe('me@example.org');

    saveMyContacts.mockResolvedValueOnce(snapshot({ version: 2, changed: true }));
    await act(async () => { await result.current.save(); });
    const [first, second] = saveMyContacts.mock.calls;
    expect(second[0]).toEqual(first[0]);
    expect(second[0].items[1].id).toBe(newId);
  });

  it('конфликт версий сохраняет черновик и даёт два выбора', async () => {
    const { result } = await ready();
    act(() => { result.current.updateRow('id-1', { value: '+79001112233' }); });
    saveMyContacts.mockRejectedValueOnce(apiError(409, 'contacts_version_conflict', { current_version: 4 }));
    const remote = snapshot({ version: 4, items: [{ ...ITEM, value: '+79995556677' }] });
    getMyContacts.mockResolvedValueOnce(remote);
    await act(async () => { await result.current.save(); });

    expect(result.current.saveState).toBe('conflict');
    expect(result.current.rows[0].value).toBe('+79001112233');
    await waitFor(() => expect(result.current.conflict.saved.version).toBe(4));

    // «Перезаписать моими правками» — версия актуальной серверной копии.
    saveMyContacts.mockResolvedValueOnce(snapshot({ version: 5, changed: true }));
    await act(async () => { await result.current.overwrite(); });
    expect(saveMyContacts).toHaveBeenLastCalledWith(expect.objectContaining({ version: 4 }));
    expect(result.current.saveState).toBe('saved');
  });

  it('«Загрузить сохранённые» заменяет черновик серверной версией', async () => {
    const { result } = await ready();
    act(() => { result.current.updateRow('id-1', { value: '+79001112233' }); });
    saveMyContacts.mockRejectedValueOnce(apiError(409, 'contacts_version_conflict', { current_version: 4 }));
    getMyContacts.mockResolvedValueOnce(
      snapshot({ version: 4, items: [{ ...ITEM, value: '+79995556677' }] }),
    );
    await act(async () => { await result.current.save(); });
    await waitFor(() => expect(result.current.conflict.saved).toBeTruthy());
    await act(async () => { await result.current.loadSaved(); });
    expect(result.current.rows[0].value).toBe('+79995556677');
    expect(result.current.version).toBe(4);
    expect(result.current.saveState).toBe('idle');
    expect(result.current.conflict).toBeNull();
  });

  it('422 от сервера подсвечивает поле, значение не теряется', async () => {
    const { result } = await ready();
    act(() => { result.current.updateRow('id-1', { value: '+79001112233' }); });
    saveMyContacts.mockRejectedValueOnce(apiError(422, 'contacts_invalid', {
      errors: [{ index: 0, field: 'value', code: 'invalid_phone' }],
    }));
    await act(async () => { await result.current.save(); });
    expect(result.current.fieldErrors['id-1'].value).toBeTruthy();
    expect(result.current.rows[0].value).toBe('+79001112233');
    expect(result.current.focusTarget).toMatchObject({ id: 'id-1', field: 'value' });
  });

  it('503 → нейтральное сообщение, черновик цел', async () => {
    const { result } = await ready();
    act(() => { result.current.updateRow('id-1', { value: '+79001112233' }); });
    saveMyContacts.mockRejectedValueOnce(apiError(503, undefined, {}));
    await act(async () => { await result.current.save(); });
    expect(result.current.saveState).toBe('error');
    expect(result.current.saveMessage).toMatch(/Повторите/);
    expect(result.current.rows[0].value).toBe('+79001112233');
  });

  it('повторное нажатие во время сохранения не шлёт второй запрос', async () => {
    const { result } = await ready();
    act(() => { result.current.updateRow('id-1', { value: '+79001112233' }); });
    const d = deferred();
    saveMyContacts.mockReturnValueOnce(d.promise);
    let p1; let p2;
    act(() => { p1 = result.current.save(); });
    act(() => { p2 = result.current.save(); });
    await act(async () => { d.resolve(snapshot({ version: 2, changed: true })); await Promise.all([p1, p2]); });
    expect(saveMyContacts).toHaveBeenCalledTimes(1);
  });

  it('revert возвращает сохранённое состояние', async () => {
    const { result } = await ready();
    act(() => { result.current.updateRow('id-1', { value: '+79001112233' }); });
    expect(result.current.dirty).toBe(true);
    act(() => { result.current.revert(); });
    expect(result.current.dirty).toBe(false);
    expect(result.current.rows[0].value).toBe('+79001234567');
  });
});

describe('useMyContacts: способ связи', () => {
  it('changeMethod задаёт type и service вместе и сбрасывает ошибки строки', async () => {
    const { result } = await ready();
    act(() => { result.current.updateRow('id-1', { value: 'abc' }); });
    await act(async () => { await result.current.save(); });
    expect(result.current.fieldErrors['id-1']).toBeTruthy();

    act(() => { result.current.changeMethod('id-1', 'messenger:telegram'); });
    expect(result.current.rows[0]).toMatchObject({ type: 'messenger', service: 'telegram', value: 'abc' });
    expect(result.current.fieldErrors['id-1']).toBeUndefined();

    act(() => { result.current.changeMethod('id-1', 'email'); });
    expect(result.current.rows[0]).toMatchObject({ type: 'email', service: '' });
  });

  it('неизвестный ключ способа связи игнорируется', async () => {
    const { result } = await ready();
    act(() => { result.current.changeMethod('id-1', 'fax:old'); });
    expect(result.current.rows[0]).toMatchObject({ type: 'phone', service: '' });
  });

  it('сохранённая подпись обычного контакта уходит в payload; новому — label:null', async () => {
    const { result } = await ready(snapshot({ items: [{ ...ITEM, label: 'рабочий' }] }));
    act(() => { result.current.addRow('phone'); });
    const newId = result.current.rows[1].id;
    act(() => { result.current.updateRow(newId, { value: '+79995556677' }); });
    saveMyContacts.mockResolvedValue(snapshot({ version: 2, changed: true }));
    await act(async () => { await result.current.save(); });
    const { items } = saveMyContacts.mock.calls[0][0];
    expect(items[0]).toMatchObject({ id: 'id-1', label: 'рабочий' });
    expect(items[1]).toMatchObject({ id: newId, label: null });
  });

  it('ошибка скрытой подписи → clearLabel → повтор уходит с label:null', async () => {
    const { result } = await ready(snapshot({ items: [{ ...ITEM, label: 'длинная подпись' }] }));
    act(() => { result.current.updateRow('id-1', { value: '+79001112233' }); });
    saveMyContacts.mockRejectedValueOnce(apiError(422, 'contacts_invalid', {
      errors: [{ index: 0, field: 'label', code: 'too_long' }],
    }));
    await act(async () => { await result.current.save(); });

    expect(result.current.fieldErrors['id-1'].hiddenLabel).toBeTruthy();
    expect(result.current.rows[0].label).toBe('длинная подпись');   // сами данные не стёрты
    expect(result.current.focusTarget).toMatchObject({ id: 'id-1', field: 'label' });

    act(() => { result.current.clearLabel('id-1'); });
    expect(result.current.rows[0].label).toBe('');
    expect(result.current.fieldErrors['id-1']).toBeUndefined();

    saveMyContacts.mockResolvedValueOnce(snapshot({
      version: 2, changed: true, items: [{ ...ITEM, value: '+79001112233' }],
    }));
    await act(async () => { await result.current.save(); });
    expect(saveMyContacts).toHaveBeenLastCalledWith({
      version: 1,
      items: [{ id: 'id-1', type: 'phone', service: null, value: '+79001112233', label: null }],
    });
    expect(result.current.saveState).toBe('saved');
  });
});
