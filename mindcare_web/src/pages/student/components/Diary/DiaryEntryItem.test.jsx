import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import * as diaryApi from '../../../../api/diary.api';
import DiaryEntryItem from './DiaryEntryItem';

jest.mock('../../../../api/diary.api');

const CATALOG = [
  { key: 'calm',    label: 'Спокойно',  sort_order: 1 },
  { key: 'focused', label: 'Сосредоточен', sort_order: 2 },
];

const entry = (overrides = {}) => ({
  uuid:       'test-uuid',
  entry_date: '2026-06-19',
  mood_score: 7,
  entry_text: 'Сегодня был хороший день',
  emotions:   ['calm'],
  created_at: '2026-06-19T10:00:00',
  updated_at: '2026-06-19T10:00:00',
  ...overrides,
});

const UPDATED_ENTRY = {
  uuid:       'test-uuid',
  entry_date: '2026-06-19',
  mood_score: 9,
  entry_text: 'обновлённый текст',
  emotions:   ['focused'],
  created_at: '2026-06-19T10:00:00',
  updated_at: '2026-06-19T11:00:00',
};

beforeEach(() => {
  jest.clearAllMocks();
  diaryApi.updateDiaryEntry.mockResolvedValue(UPDATED_ENTRY);
  diaryApi.deleteDiaryEntry.mockResolvedValue(undefined);
});

// ─── helpers: open action menu and trigger actions ────────────────────────────

function openEditViaMenu() {
  fireEvent.click(screen.getByRole('button', { name: /действия с записью/i }));
  fireEvent.click(
    within(screen.getByTestId('entry-action-sheet')).getByRole('button', { name: /редактировать запись/i })
  );
}

function openDeleteConfirmViaMenu() {
  fireEvent.click(screen.getByRole('button', { name: /действия с записью/i }));
  fireEvent.click(
    within(screen.getByTestId('entry-action-sheet')).getByRole('button', { name: /удалить запись/i })
  );
}

// ─── read view ────────────────────────────────────────────────────────────────

test('formats date using local timezone — day number matches ISO date', () => {
  render(<DiaryEntryItem entry={entry()} emotionCatalog={[]} />);
  expect(screen.getByText(/19/)).toBeInTheDocument();
});

test('renders mood score and word from MOOD_WORDS', () => {
  render(<DiaryEntryItem entry={entry()} emotionCatalog={[]} />);
  expect(screen.getByText(/7\/10/)).toBeInTheDocument();
  expect(screen.getByText(/Хорошо/)).toBeInTheDocument();
});

test('maps emotion key to label via catalog', () => {
  render(<DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} />);
  expect(screen.getByText('Спокойно')).toBeInTheDocument();
});

test('shows raw key when emotion is not in catalog', () => {
  render(<DiaryEntryItem entry={entry({ emotions: ['unknown_key'] })} emotionCatalog={[]} />);
  expect(screen.getByText('unknown_key')).toBeInTheDocument();
});

test('renders entry text', () => {
  render(<DiaryEntryItem entry={entry()} emotionCatalog={[]} />);
  expect(screen.getByText('Сегодня был хороший день')).toBeInTheDocument();
});

// ─── action menu trigger (kebab) ──────────────────────────────────────────────

test('no kebab button when onUpdate and onDelete not provided', () => {
  render(<DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} />);
  expect(screen.queryByRole('button', { name: /действия с записью/i })).not.toBeInTheDocument();
});

test('shows kebab button when both callbacks provided', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  expect(screen.getByRole('button', { name: /действия с записью/i })).toBeInTheDocument();
});

test('shows kebab button when only onUpdate provided', () => {
  render(<DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} />);
  expect(screen.getByRole('button', { name: /действия с записью/i })).toBeInTheDocument();
});

test('read mode does not render persistent edit/delete icon buttons outside menu', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  // buttons only appear inside the menu (closed by default)
  expect(screen.queryByRole('button', { name: /редактировать запись/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /удалить запись/i })).not.toBeInTheDocument();
});

test('read mode does not render text "Изменить"', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  expect(screen.queryByText('Изменить')).not.toBeInTheDocument();
});

test('read mode does not render text "Удалить" when menu is closed', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  expect(screen.queryByText('Удалить')).not.toBeInTheDocument();
});

// ─── action menu contents ─────────────────────────────────────────────────────

test('action menu is not visible initially', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  expect(screen.queryByTestId('entry-action-sheet')).not.toBeInTheDocument();
});

test('clicking kebab opens action menu', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  fireEvent.click(screen.getByRole('button', { name: /действия с записью/i }));
  expect(screen.getByTestId('entry-action-sheet')).toBeInTheDocument();
});

test('action menu contains Редактировать запись, Удалить запись and Отмена', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  fireEvent.click(screen.getByRole('button', { name: /действия с записью/i }));
  const menu = screen.getByTestId('entry-action-sheet');
  expect(within(menu).getByRole('button', { name: /редактировать запись/i })).toBeInTheDocument();
  expect(within(menu).getByRole('button', { name: /удалить запись/i })).toBeInTheDocument();
  expect(within(menu).getByRole('button', { name: /отмена/i })).toBeInTheDocument();
});

test('menu shows only edit when only onUpdate provided', () => {
  render(<DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: /действия с записью/i }));
  const menu = screen.getByTestId('entry-action-sheet');
  expect(within(menu).getByRole('button', { name: /редактировать запись/i })).toBeInTheDocument();
  expect(within(menu).queryByRole('button', { name: /удалить запись/i })).not.toBeInTheDocument();
});

test('clicking kebab again closes the menu', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  const kebab = screen.getByRole('button', { name: /действия с записью/i });
  fireEvent.click(kebab);
  expect(screen.getByTestId('entry-action-sheet')).toBeInTheDocument();
  fireEvent.click(kebab);
  expect(screen.queryByTestId('entry-action-sheet')).not.toBeInTheDocument();
});

test('"Отмена" in menu closes it', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  fireEvent.click(screen.getByRole('button', { name: /действия с записью/i }));
  const menu = screen.getByTestId('entry-action-sheet');
  fireEvent.click(within(menu).getByRole('button', { name: /отмена/i }));
  expect(screen.queryByTestId('entry-action-sheet')).not.toBeInTheDocument();
});

test('Escape key closes action menu', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  fireEvent.click(screen.getByRole('button', { name: /действия с записью/i }));
  expect(screen.getByTestId('entry-action-sheet')).toBeInTheDocument();
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(screen.queryByTestId('entry-action-sheet')).not.toBeInTheDocument();
});

test('"Редактировать запись" in menu closes menu and opens edit mode', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openEditViaMenu();
  expect(screen.queryByTestId('entry-action-sheet')).not.toBeInTheDocument();
  expect(screen.getByText('Редактирование')).toBeInTheDocument();
});

test('"Удалить запись" in menu opens delete confirm without immediate API call', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openDeleteConfirmViaMenu();
  expect(screen.queryByTestId('entry-action-sheet')).not.toBeInTheDocument();
  expect(screen.getByText(/удалить запись за/i)).toBeInTheDocument();
  expect(diaryApi.deleteDiaryEntry).not.toHaveBeenCalled();
});

// ─── edit mode ────────────────────────────────────────────────────────────────

test('clicking Редактировать запись opens edit form', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openEditViaMenu();
  expect(screen.getByText('Редактирование')).toBeInTheDocument();
  expect(screen.getByRole('slider', { name: /настроение/i })).toBeInTheDocument();
});

test('edit form pre-fills mood from entry', () => {
  render(
    <DiaryEntryItem entry={entry({ mood_score: 7 })} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openEditViaMenu();
  expect(screen.getByRole('slider', { name: /настроение/i })).toHaveValue('7');
});

test('edit form pre-fills entry_text from entry', () => {
  render(
    <DiaryEntryItem entry={entry({ entry_text: 'Мой дневниковый текст' })} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openEditViaMenu();
  expect(screen.getByDisplayValue('Мой дневниковый текст')).toBeInTheDocument();
});

test('edit form pre-fills emotions from entry', () => {
  render(
    <DiaryEntryItem entry={entry({ emotions: ['calm'] })} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openEditViaMenu();
  const calmBtn = screen.getByRole('button', { name: 'Спокойно' });
  expect(calmBtn).toHaveAttribute('aria-pressed', 'true');
});

test('cancel edit returns to read view', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openEditViaMenu();
  expect(screen.getByText('Редактирование')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /отмена/i }));
  expect(screen.queryByText('Редактирование')).not.toBeInTheDocument();
  expect(screen.getByText(/7\/10/)).toBeInTheDocument();
});

test('save edit calls updateDiaryEntry with uuid and payload', async () => {
  render(
    <DiaryEntryItem entry={entry({ mood_score: 7 })} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openEditViaMenu();

  const slider = screen.getByRole('slider', { name: /настроение/i });
  fireEvent.change(slider, { target: { value: '9' } });

  fireEvent.click(screen.getByRole('button', { name: /сохранить/i }));

  await waitFor(() =>
    expect(diaryApi.updateDiaryEntry).toHaveBeenCalledWith(
      'test-uuid',
      expect.objectContaining({ mood_score: 9 })
    )
  );
});

test('successful save calls onUpdate with updated entry', async () => {
  const onUpdate = jest.fn();
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={onUpdate} onDelete={jest.fn()} />
  );
  openEditViaMenu();
  fireEvent.click(screen.getByRole('button', { name: /сохранить/i }));

  await waitFor(() => expect(onUpdate).toHaveBeenCalledWith(UPDATED_ENTRY));
  expect(screen.queryByText('Редактирование')).not.toBeInTheDocument();
});

test('save error shows error message and stays in edit mode', async () => {
  diaryApi.updateDiaryEntry.mockRejectedValue(new Error('Ошибка сети'));
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openEditViaMenu();
  fireEvent.click(screen.getByRole('button', { name: /сохранить/i }));

  expect(await screen.findByText('Ошибка сети')).toBeInTheDocument();
  expect(screen.getByText('Редактирование')).toBeInTheDocument();
});

test('save button disabled and shows Сохранение… while saving', async () => {
  diaryApi.updateDiaryEntry.mockReturnValue(new Promise(() => {}));
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openEditViaMenu();
  fireEvent.click(screen.getByRole('button', { name: /сохранить/i }));

  await waitFor(() =>
    expect(screen.getByText('Сохранение…')).toBeDisabled()
  );
});

// ─── delete confirm mode ──────────────────────────────────────────────────────

test('clicking Удалить запись opens delete confirmation', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openDeleteConfirmViaMenu();
  expect(screen.getByText(/удалить запись за/i)).toBeInTheDocument();
  expect(screen.getByText(/это действие скроет/i)).toBeInTheDocument();
});

test('cancel delete returns to read view', () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openDeleteConfirmViaMenu();
  fireEvent.click(screen.getByRole('button', { name: /отмена/i }));
  expect(screen.queryByText(/удалить запись за/i)).not.toBeInTheDocument();
  expect(screen.getByText(/7\/10/)).toBeInTheDocument();
});

test('confirm delete calls deleteDiaryEntry with entry uuid', async () => {
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openDeleteConfirmViaMenu();
  fireEvent.click(screen.getByRole('button', { name: /^удалить$/i }));

  await waitFor(() =>
    expect(diaryApi.deleteDiaryEntry).toHaveBeenCalledWith('test-uuid')
  );
});

test('successful delete calls onDelete with uuid', async () => {
  const onDelete = jest.fn();
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={onDelete} />
  );
  openDeleteConfirmViaMenu();
  fireEvent.click(screen.getByRole('button', { name: /^удалить$/i }));

  await waitFor(() => expect(onDelete).toHaveBeenCalledWith('test-uuid'));
});

test('delete error shows error message and keeps item visible', async () => {
  diaryApi.deleteDiaryEntry.mockRejectedValue(new Error('Не удалось удалить'));
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openDeleteConfirmViaMenu();
  fireEvent.click(screen.getByRole('button', { name: /^удалить$/i }));

  expect(await screen.findByText('Не удалось удалить')).toBeInTheDocument();
  expect(screen.getByText(/удалить запись за/i)).toBeInTheDocument();
});

test('delete button disabled and shows Удаление… while deleting', async () => {
  diaryApi.deleteDiaryEntry.mockReturnValue(new Promise(() => {}));
  render(
    <DiaryEntryItem entry={entry()} emotionCatalog={CATALOG} onUpdate={jest.fn()} onDelete={jest.fn()} />
  );
  openDeleteConfirmViaMenu();
  fireEvent.click(screen.getByRole('button', { name: /^удалить$/i }));

  await waitFor(() =>
    expect(screen.getByText('Удаление…')).toBeDisabled()
  );
});
