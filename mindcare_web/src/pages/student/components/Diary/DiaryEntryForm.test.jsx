import { render, screen, fireEvent } from '@testing-library/react';
import DiaryEntryForm from './DiaryEntryForm';

const EMOTIONS = [
  { key: 'calm',  label: 'Спокойно', sort_order: 1 },
  { key: 'happy', label: 'Радостно', sort_order: 2 },
];

function renderForm(props = {}) {
  const defaults = {
    emotions: EMOTIONS,
    text: '',
    onTextChange: jest.fn(),
    selectedEmotions: [],
    onEmotionToggle: jest.fn(),
    moodSelected: true,
    isExistingEntry: false,
    saving: false,
    showSaved: false,
    saveError: null,
    onSave: jest.fn(),
  };
  return render(<DiaryEntryForm {...defaults} {...props} />);
}

// ─── emotion chips ────────────────────────────────────────────────────────────

test('renders emotion chips from emotions prop', () => {
  renderForm();
  expect(screen.getByRole('button', { name: 'Спокойно' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Радостно' })).toBeInTheDocument();
});

test('emotion chip click calls onEmotionToggle with the key', () => {
  const onEmotionToggle = jest.fn();
  renderForm({ onEmotionToggle });
  fireEvent.click(screen.getByRole('button', { name: 'Спокойно' }));
  expect(onEmotionToggle).toHaveBeenCalledWith('calm');
});

test('selected emotion chip has aria-pressed=true', () => {
  renderForm({ selectedEmotions: ['calm'] });
  expect(screen.getByRole('button', { name: 'Спокойно' })).toHaveAttribute('aria-pressed', 'true');
});

test('unselected emotion chip has aria-pressed=false', () => {
  renderForm({ selectedEmotions: ['calm'] });
  expect(screen.getByRole('button', { name: 'Радостно' })).toHaveAttribute('aria-pressed', 'false');
});

test('emotion section shows "Что вы чувствуете?"', () => {
  renderForm();
  expect(screen.getByText('Что вы чувствуете?')).toBeInTheDocument();
});

test('emotion section shows "Можно выбрать несколько."', () => {
  renderForm();
  expect(screen.getByText('Можно выбрать несколько.')).toBeInTheDocument();
});

// ─── collapsible details ──────────────────────────────────────────────────────

test('details textarea hidden by default when text is empty', () => {
  renderForm({ text: '' });
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});

test('shows "+ Добавить подробности" toggle when details are closed', () => {
  renderForm({ text: '' });
  expect(screen.getByRole('button', { name: /добавить подробности/i })).toBeInTheDocument();
});

test('clicking toggle opens details textarea', () => {
  renderForm({ text: '' });
  fireEvent.click(screen.getByRole('button', { name: /добавить подробности/i }));
  expect(screen.getByRole('textbox')).toBeInTheDocument();
});

test('details shown by default when text prop is non-empty', () => {
  renderForm({ text: 'Хорошее настроение' });
  expect(screen.getByRole('textbox')).toBeInTheDocument();
});

test('shows "Скрыть подробности" when details are open', () => {
  renderForm({ text: 'Хорошее настроение' });
  expect(screen.getByRole('button', { name: /скрыть подробности/i })).toBeInTheDocument();
});

test('clicking "Скрыть подробности" closes the details textarea', () => {
  renderForm({ text: 'Хорошее настроение' });
  fireEvent.click(screen.getByRole('button', { name: /скрыть подробности/i }));
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});

test('textarea has updated placeholder about discussion with psychologist', () => {
  renderForm({ text: '' });
  fireEvent.click(screen.getByRole('button', { name: /добавить подробности/i }));
  expect(screen.getByRole('textbox')).toHaveAttribute(
    'placeholder',
    'Что повлияло на состояние? Что хочется обсудить с психологом?'
  );
});

// ─── button labels ────────────────────────────────────────────────────────────

test('submit button shows "Сохранить отметку" for new entry', () => {
  renderForm({ isExistingEntry: false });
  expect(screen.getByRole('button', { name: 'Сохранить отметку' })).toBeInTheDocument();
});

test('submit button shows "Обновить запись" for existing entry', () => {
  renderForm({ isExistingEntry: true });
  expect(screen.getByRole('button', { name: 'Обновить запись' })).toBeInTheDocument();
});

test('submit button shows "✓ Сохранено" when showSaved is true', () => {
  renderForm({ showSaved: true });
  expect(screen.getByRole('button', { name: /Сохранено/ })).toBeInTheDocument();
});

test('submit button shows "Сохранение…" when saving is true', () => {
  renderForm({ saving: true });
  expect(screen.getByRole('button', { name: 'Сохранение…' })).toBeInTheDocument();
});

// ─── disabled / hints ─────────────────────────────────────────────────────────

test('submit button is disabled when moodSelected is false', () => {
  renderForm({ moodSelected: false });
  expect(screen.getByRole('button', { name: 'Сохранить отметку' })).toBeDisabled();
});

test('shows mood hint when mood is not selected', () => {
  renderForm({ moodSelected: false });
  expect(screen.getByText(/выберите состояние на шкале/i)).toBeInTheDocument();
});

test('mood hint is not shown when mood is selected', () => {
  renderForm({ moodSelected: true });
  expect(screen.queryByText(/выберите состояние на шкале/i)).not.toBeInTheDocument();
});

// ─── errors ───────────────────────────────────────────────────────────────────

test('shows saveError message when provided', () => {
  renderForm({ saveError: 'Не удалось сохранить запись.' });
  expect(screen.getByText('Не удалось сохранить запись.')).toBeInTheDocument();
});

test('does not show error block when saveError is null', () => {
  renderForm({ saveError: null });
  expect(screen.queryByText(/не удалось сохранить/i)).not.toBeInTheDocument();
});

// ─── copy guard ───────────────────────────────────────────────────────────────

test('form does not contain "каждый день"', () => {
  renderForm();
  expect(screen.queryByText(/каждый день/i)).not.toBeInTheDocument();
});
