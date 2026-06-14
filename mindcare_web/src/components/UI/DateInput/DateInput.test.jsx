import { render, screen, fireEvent } from '@testing-library/react';
import DateInput from './DateInput';

test('показывает placeholder при пустом значении', () => {
  render(<DateInput value="" onChange={() => {}} placeholder="дд.мм.гггг" />);
  expect(screen.getByText('дд.мм.гггг')).toBeInTheDocument();
});

test('отображает выбранную дату как дд.мм.гггг', () => {
  render(<DateInput value="2026-06-14" onChange={() => {}} />);
  expect(screen.getByText('14.06.2026')).toBeInTheDocument();
});

test('выбор дня вызывает onChange с YYYY-MM-DD', () => {
  const onChange = jest.fn();
  render(<DateInput value="2026-06-10" onChange={onChange} />);

  // открыть popover (клик по полю с текущим значением)
  fireEvent.click(screen.getByText('10.06.2026'));

  // popover открыт на июне 2026 — выбрать 15-е число
  fireEvent.click(screen.getByRole('button', { name: '15' }));

  expect(onChange).toHaveBeenCalledWith('2026-06-15');
});

test('кнопка очистки вызывает onChange("")', () => {
  const onChange = jest.fn();
  render(<DateInput value="2026-06-14" onChange={onChange} />);

  fireEvent.click(screen.getByLabelText('Очистить дату'));

  expect(onChange).toHaveBeenCalledWith('');
});

test('навигация по месяцам меняет заголовок', () => {
  render(<DateInput value="2026-06-10" onChange={() => {}} />);
  fireEvent.click(screen.getByText('10.06.2026'));

  expect(screen.getByText('Июнь 2026')).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('Следующий месяц'));
  expect(screen.getByText('Июль 2026')).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('Предыдущий месяц'));
  fireEvent.click(screen.getByLabelText('Предыдущий месяц'));
  expect(screen.getByText('Май 2026')).toBeInTheDocument();
});
