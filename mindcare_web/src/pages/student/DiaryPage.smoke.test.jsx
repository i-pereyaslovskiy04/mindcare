import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import * as diaryApi from '../../api/diary.api';
import DiaryPage from './DiaryPage';

jest.mock('../../api/diary.api');
jest.mock('react-router-dom', () => ({
  Link: ({ to, children }) => <a href={to}>{children}</a>,
}), { virtual: true });

const MOCK_EMOTIONS = [
  { key: 'calm',   label: 'Спокойно', sort_order: 1 },
  { key: 'joyful', label: 'Радостно', sort_order: 2 },
];

const EMPTY_TODAY = {
  entry_date: '2026-06-18',
  mood_score: null,
  entry_text: '',
  emotions: [],
};

const FILLED_TODAY = {
  entry_date: '2026-06-18',
  mood_score: 7,
  entry_text: 'Хороший день',
  emotions: ['calm'],
};

const MOCK_SUMMARY = {
  period: '14d',
  entries_count: 3,
  points: Array.from({ length: 14 }, (_, i) => ({
    date: `2026-06-${String(i + 10).padStart(2, '0')}`,
    label: String(i + 10),
    mood_score: i < 3 ? 6 : null,
  })),
};

const MOCK_ENTRIES_RESP = {
  items: [
    {
      uuid: 'abc123',
      entry_date: '2026-06-17',
      mood_score: 5,
      entry_text: 'Вчера был хороший день',
      emotions: ['calm'],
      created_at: '2026-06-17T10:00:00',
      updated_at: '2026-06-17T10:00:00',
    },
  ],
  total: 1,
  limit: 4,
  offset: 0,
};

beforeEach(() => {
  jest.clearAllMocks();
  diaryApi.getDiaryEmotions.mockResolvedValue(MOCK_EMOTIONS);
  diaryApi.getTodayDiaryEntry.mockResolvedValue(EMPTY_TODAY);
  diaryApi.getDiaryEntries.mockResolvedValue(MOCK_ENTRIES_RESP);
  diaryApi.saveTodayDiaryEntry.mockResolvedValue(FILLED_TODAY);
  diaryApi.getDiarySummary.mockResolvedValue(MOCK_SUMMARY);
});

// ─── mount + data loading ─────────────────────────────────────────────────────

test('calls emotions, today, entries APIs on mount', async () => {
  render(<DiaryPage />);
  await waitFor(() => expect(diaryApi.getDiaryEmotions).toHaveBeenCalledTimes(1));
  expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1);
  expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(1);
});

test('renders emotion chips from API after load', async () => {
  render(<DiaryPage />);
  // "Что вы чувствуете?" is the new emotion section label — appears once load is complete
  expect(await screen.findByText('Что вы чувствуете?')).toBeInTheDocument();
  expect(screen.getAllByText('Спокойно').length).toBeGreaterThan(0);
  expect(screen.getByText('Радостно')).toBeInTheDocument();
});

test('new entry defaults to mood 5 — shows Нейтрально, not Выберите настроение', async () => {
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');
  expect(screen.getByText('Нейтрально')).toBeInTheDocument();
  expect(screen.queryByText('Выберите настроение')).not.toBeInTheDocument();
});

test('emotion chips from API props — custom emotion key appears as label', async () => {
  diaryApi.getDiaryEmotions.mockResolvedValue([
    { key: 'custom_key', label: 'Уникальная эмоция', sort_order: 1 },
  ]);
  render(<DiaryPage />);
  expect(await screen.findByText('Уникальная эмоция')).toBeInTheDocument();
});

// ─── save flow ────────────────────────────────────────────────────────────────

test('submit calls saveTodayDiaryEntry with mood_score and selected emotions', async () => {
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');

  // Set mood via range slider
  const slider = screen.getByRole('slider', { name: /настроения/i });
  fireEvent.change(slider, { target: { value: '7' } });

  // Select emotion chip
  const chips = screen.getAllByRole('button', { name: 'Спокойно' });
  fireEvent.click(chips[0]);

  // New entry — button label is "Сохранить отметку"
  const saveBtn = screen.getByRole('button', { name: /сохранить отметку/i });
  fireEvent.click(saveBtn);

  await waitFor(() =>
    expect(diaryApi.saveTodayDiaryEntry).toHaveBeenCalledWith(
      expect.objectContaining({ mood_score: 7, emotions: ['calm'] })
    )
  );
});

test('after save, getDiaryEntries is called a second time', async () => {
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');

  const slider = screen.getByRole('slider', { name: /настроения/i });
  fireEvent.change(slider, { target: { value: '7' } });

  const saveBtn = screen.getByRole('button', { name: /сохранить отметку/i });
  fireEvent.click(saveBtn);

  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2));
});

// ─── history ─────────────────────────────────────────────────────────────────

test('history entry text is shown and emotion key is mapped to label', async () => {
  render(<DiaryPage />);
  expect(await screen.findByText('Вчера был хороший день')).toBeInTheDocument();
  expect(screen.getAllByText('Спокойно').length).toBeGreaterThan(0);
});

test('unknown emotion key in history shows the key itself without crashing', async () => {
  diaryApi.getDiaryEntries.mockResolvedValue({
    items: [
      {
        uuid: 'u1',
        entry_date: '2026-06-17',
        mood_score: 5,
        entry_text: '',
        emotions: ['unknown_xyz_key'],
        created_at: '2026-06-17T10:00:00',
        updated_at: '2026-06-17T10:00:00',
      },
    ],
    total: 1,
    limit: 4,
    offset: 0,
  });
  render(<DiaryPage />);
  expect(await screen.findByText('unknown_xyz_key')).toBeInTheDocument();
});

// ─── error handling ───────────────────────────────────────────────────────────

test('shows load error message when API fails, with retry button', async () => {
  diaryApi.getDiaryEmotions.mockRejectedValue(new Error('Ошибка сети'));
  diaryApi.getTodayDiaryEntry.mockRejectedValue(new Error('Ошибка сети'));
  diaryApi.getDiaryEntries.mockRejectedValue(new Error('Ошибка сети'));
  render(<DiaryPage />);
  expect(await screen.findByText(/ошибка/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /повторить/i })).toBeInTheDocument();
});

test('shows save error inline after failed save', async () => {
  diaryApi.saveTodayDiaryEntry.mockRejectedValue(new Error('Ошибка сохранения'));
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');

  const slider = screen.getByRole('slider', { name: /настроения/i });
  fireEvent.change(slider, { target: { value: '7' } });

  // Open details so textarea is visible, then type text
  fireEvent.click(screen.getByRole('button', { name: /добавить подробности/i }));
  const textarea = screen.getByPlaceholderText(/что повлияло на состояние/i);
  fireEvent.change(textarea, { target: { value: 'Мой текст' } });

  const saveBtn = screen.getByRole('button', { name: /сохранить отметку/i });
  fireEvent.click(saveBtn);

  expect(await screen.findByText('Ошибка сохранения')).toBeInTheDocument();
  expect(screen.getByDisplayValue('Мой текст')).toBeInTheDocument();
});

// ─── submit button state ──────────────────────────────────────────────────────

test('submit button is enabled for new entry with default mood 5', async () => {
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');
  const submitBtn = screen.getByRole('button', { name: /сохранить отметку/i });
  expect(submitBtn).not.toBeDisabled();
});

test('submit button remains enabled after slider is moved to a different value', async () => {
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');

  const slider = screen.getByRole('slider', { name: /настроения/i });
  fireEvent.change(slider, { target: { value: '6' } });

  await waitFor(() =>
    expect(screen.getByRole('button', { name: /сохранить отметку/i })).not.toBeDisabled()
  );
});

// ─── history preview footer link ──────────────────────────────────────────────

test('"Смотреть всю историю" link is shown when there are entries', async () => {
  // default: MOCK_ENTRIES_RESP has total: 1
  render(<DiaryPage />);
  expect(await screen.findByText('Вчера был хороший день')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Смотреть всю историю/i })).toBeInTheDocument();
});

test('"Смотреть всю историю" link is not shown when total is 0', async () => {
  diaryApi.getDiaryEntries.mockResolvedValue({ items: [], total: 0, limit: 4, offset: 0 });
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');
  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole('link', { name: /Смотреть всю историю/i })).not.toBeInTheDocument();
});

test('"Загрузить ещё" button is not shown on main diary page', async () => {
  diaryApi.getDiaryEntries.mockResolvedValue({
    items: [MOCK_ENTRIES_RESP.items[0]],
    total: 10,
    limit: 4,
    offset: 0,
  });
  render(<DiaryPage />);
  await screen.findByText('Вчера был хороший день');
  expect(screen.queryByRole('button', { name: /загрузить ещё/i })).not.toBeInTheDocument();
});

// ─── observation block ────────────────────────────────────────────────────────

test('observation block "Самонаблюдение" heading renders after load', async () => {
  render(<DiaryPage />);
  expect(await screen.findByText('Самонаблюдение')).toBeInTheDocument();
});

test('period chips 14 дней / Месяц / Год are visible', async () => {
  render(<DiaryPage />);
  await screen.findByText('Самонаблюдение');
  expect(screen.getByRole('button', { name: '14 дней' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Месяц' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Год' })).toBeInTheDocument();
});

test('getDiarySummary is called with "14d" on mount', async () => {
  render(<DiaryPage />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('14d'));
});

test('clicking "Месяц" calls getDiarySummary with "month"', async () => {
  render(<DiaryPage />);
  await screen.findByText('Самонаблюдение');

  fireEvent.click(screen.getByRole('button', { name: 'Месяц' }));

  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('month'));
});
