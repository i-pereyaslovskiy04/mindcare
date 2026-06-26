import { render, screen, fireEvent } from '@testing-library/react';
import MoodSelector from './MoodSelector';

// ─── scale labels ─────────────────────────────────────────────────────────────

test('scale label left shows "1 · тяжело"', () => {
  render(<MoodSelector value={5} onChange={jest.fn()} />);
  expect(screen.getByText('1 · тяжело')).toBeInTheDocument();
});

test('scale label center shows "5–6 · нейтрально"', () => {
  render(<MoodSelector value={5} onChange={jest.fn()} />);
  expect(screen.getByText('5–6 · нейтрально')).toBeInTheDocument();
});

test('scale label right shows "10 · светло"', () => {
  render(<MoodSelector value={5} onChange={jest.fn()} />);
  expect(screen.getByText('10 · светло')).toBeInTheDocument();
});

// ─── value=5 (default state) ──────────────────────────────────────────────────

test('shows mood word "Нейтрально" for value 5', () => {
  render(<MoodSelector value={5} onChange={jest.fn()} />);
  expect(screen.getByText('Нейтрально')).toBeInTheDocument();
});

test('shows score "5" and "из 10" for value 5', () => {
  render(<MoodSelector value={5} onChange={jest.fn()} />);
  expect(screen.getByText('5')).toBeInTheDocument();
  expect(screen.getByText('из 10')).toBeInTheDocument();
});

test('slider has value "5" when value prop is 5', () => {
  render(<MoodSelector value={5} onChange={jest.fn()} />);
  expect(screen.getByRole('slider')).toHaveValue('5');
});

// ─── null value fallback ──────────────────────────────────────────────────────

test('shows "Выберите настроение" when value is null', () => {
  render(<MoodSelector value={null} onChange={jest.fn()} />);
  expect(screen.getByText('Выберите настроение')).toBeInTheDocument();
});

test('shows "—" in score display when value is null', () => {
  render(<MoodSelector value={null} onChange={jest.fn()} />);
  expect(screen.getByText('—')).toBeInTheDocument();
});

test('slider defaults to position 5 when value is null', () => {
  render(<MoodSelector value={null} onChange={jest.fn()} />);
  expect(screen.getByRole('slider')).toHaveValue('5');
});

// ─── other values ────────────────────────────────────────────────────────────

test('shows "Хорошо" for value 7', () => {
  render(<MoodSelector value={7} onChange={jest.fn()} />);
  expect(screen.getByText('Хорошо')).toBeInTheDocument();
});

test('onChange called with numeric value when slider changes', () => {
  const onChange = jest.fn();
  render(<MoodSelector value={5} onChange={onChange} />);
  fireEvent.change(screen.getByRole('slider'), { target: { value: '8' } });
  expect(onChange).toHaveBeenCalledWith(8);
});
