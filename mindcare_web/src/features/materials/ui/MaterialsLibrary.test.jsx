import { act, fireEvent, render, screen, within } from '@testing-library/react';
import MaterialsLibrary from './MaterialsLibrary';
import { getArticles, getPublicCategories } from '../../../api/articles.api';

jest.mock('../../../api/articles.api');
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });

const article = (n) => ({
  uuid: `uuid-${n}`, title: `Материал ${n}`, excerpt: '', published_at: '2026-10-01T09:00:00Z',
  categories: [], tags: [],
});

let mobile = false;

beforeAll(() => {
  window.matchMedia = (query) => ({
    matches: mobile, media: query, addEventListener: () => {}, removeEventListener: () => {},
  });
});

beforeEach(() => {
  jest.clearAllMocks();
  mobile = false;
  getPublicCategories.mockResolvedValue([{ id: 3, name: 'Статья' }, { id: 4, name: 'Гид' }]);
});

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

describe('MaterialsLibrary — debounce поиска', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it('ввод, правка и возврат к тому же запросу за время debounce не очищают результаты', async () => {
    getArticles.mockResolvedValue({ items: [article(1)], total: 1 });
    render(<MaterialsLibrary getItemPath={id => `/m/${id}`} />);
    await flush();

    const input = screen.getByRole('textbox', { name: 'Поиск по материалам' });
    fireEvent.change(input, { target: { value: 'сон' } });
    await act(async () => { jest.advanceTimersByTime(300); });
    await flush();
    expect(getArticles).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'сон', page: 1 }));
    expect(screen.getByRole('link', { name: 'Читать: Материал 1' })).toBeInTheDocument();
    const calls = getArticles.mock.calls.length;

    // «сонx» → «сон» быстрее 300 мс: в итоге тот же запрос
    fireEvent.change(input, { target: { value: 'сонx' } });
    await act(async () => { jest.advanceTimersByTime(100); });
    fireEvent.change(input, { target: { value: 'сон' } });
    await act(async () => { jest.advanceTimersByTime(300); });
    await flush();
    expect(getArticles).toHaveBeenCalledTimes(calls);
    expect(screen.getByRole('link', { name: 'Читать: Материал 1' })).toBeInTheDocument();
    expect(screen.queryByText(/ничего не найдено/i)).toBeNull();

    // тот же запрос с пробелами — тоже без очистки
    fireEvent.change(input, { target: { value: ' сон ' } });
    await act(async () => { jest.advanceTimersByTime(300); });
    await flush();
    expect(getArticles).toHaveBeenCalledTimes(calls);
    expect(screen.getByRole('link', { name: 'Читать: Материал 1' })).toBeInTheDocument();
  });
});

describe('MaterialsLibrary — мобильная панель фильтров и клавиатура', () => {
  beforeEach(() => {
    mobile = true;
    getArticles.mockResolvedValue({ items: [article(1)], total: 1 });
  });

  async function openSheet() {
    render(<MaterialsLibrary getItemPath={id => `/m/${id}`} />);
    const trigger = await screen.findByRole('button', { name: 'Фильтры' });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Фильтры' });
    // фокус обязан уйти в диалог (первый контрол), иначе проверка возврата была бы пустой
    const close = within(dialog).getByRole('button', { name: 'Закрыть панель фильтров' });
    expect(trigger).not.toHaveFocus();
    expect(close).toHaveFocus();
    return { trigger, dialog, close };
  }

  it('при открытии фокус внутри диалога; Tab / Shift+Tab циклически внутри', async () => {
    const { dialog, close } = await openSheet();
    const last = within(dialog).getByRole('button', { name: 'Гид' });

    fireEvent.keyDown(close, { key: 'Tab', shiftKey: true });
    expect(last).toHaveFocus();
    fireEvent.keyDown(last, { key: 'Tab' });
    expect(close).toHaveFocus();
  });

  it('Escape закрывает и возвращает фокус на кнопку «Фильтры»', async () => {
    const { trigger, close } = await openSheet();
    fireEvent.keyDown(close, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Фильтры' })).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it('«Закрыть» возвращает фокус на кнопку «Фильтры»', async () => {
    const { trigger, close } = await openSheet();
    fireEvent.click(close);
    expect(screen.queryByRole('dialog', { name: 'Фильтры' })).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it('выбор типа в панели уходит на сервер, фокус остаётся в диалоге', async () => {
    const { dialog } = await openSheet();
    const chip = within(dialog).getByRole('button', { name: 'Статья' });
    chip.focus();
    fireEvent.click(chip);
    await flush();
    expect(getArticles).toHaveBeenLastCalledWith(expect.objectContaining({ category_id: 3, page: 1 }));
    expect(chip).toHaveFocus();
    expect(screen.getByRole('dialog', { name: 'Фильтры' })).toContainElement(chip);
  });
});
