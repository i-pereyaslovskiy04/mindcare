import { createRef } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import CodeInput from './CodeInput';

const EMPTY = ['', '', '', '', '', ''];

function setup(props = {}) {
  const onChange = jest.fn();
  const utils = render(<CodeInput value={EMPTY} onChange={onChange} {...props} />);
  const cells = () => within(screen.getByRole('group', { name: 'Код подтверждения' })).getAllByRole('textbox');
  return { onChange, cells, ...utils };
}

test('шесть ячеек, первая — автозаполнение одноразового кода, цифровая клавиатура', () => {
  const { cells } = setup();
  expect(cells()).toHaveLength(6);
  expect(cells()[0]).toHaveAttribute('autocomplete', 'one-time-code');
  cells().slice(1).forEach((c) => expect(c).toHaveAttribute('autocomplete', 'off'));
  cells().forEach((c) => expect(c).toHaveAttribute('inputmode', 'numeric'));
});

test('ввод цифры записывает её и переводит фокус дальше; буквы отбрасываются', () => {
  const { cells, onChange } = setup();
  fireEvent.change(cells()[0], { target: { value: '7' } });
  expect(onChange).toHaveBeenLastCalledWith(['7', '', '', '', '', '']);
  expect(cells()[1]).toHaveFocus();
  fireEvent.change(cells()[1], { target: { value: 'a' } });
  expect(onChange).toHaveBeenLastCalledWith(['', '', '', '', '', '']);
});

test('вставка кода раскладывает цифры по ячейкам (нецифровые символы отброшены)', () => {
  const { cells, onChange } = setup();
  fireEvent.paste(cells()[0], { clipboardData: { getData: () => '01 23-45' } });
  expect(onChange).toHaveBeenLastCalledWith(['0', '1', '2', '3', '4', '5']);
  expect(cells()[5]).toHaveFocus();
});

test('вставка полного кода в любую ячейку заполняет код с начала', () => {
  const { cells, onChange } = setup();
  fireEvent.paste(cells()[3], { clipboardData: { getData: () => '482915' } });
  expect(onChange).toHaveBeenLastCalledWith(['4', '8', '2', '9', '1', '5']);
});

test('частичная вставка — с текущей ячейки', () => {
  const { cells, onChange } = setup();
  fireEvent.paste(cells()[2], { clipboardData: { getData: () => '91' } });
  expect(onChange).toHaveBeenLastCalledWith(['', '', '9', '1', '', '']);
});

test('автозаполнение телефоном: весь код в первой ячейке раскладывается по ячейкам', () => {
  const { cells, onChange } = setup();
  fireEvent.change(cells()[0], { target: { value: '004219' } });
  expect(onChange).toHaveBeenLastCalledWith(['0', '0', '4', '2', '1', '9']);
});

test('ввод поверх цифры заменяет её', () => {
  const { cells, onChange } = setup({ value: ['3', '', '', '', '', ''] });
  fireEvent.change(cells()[0], { target: { value: '35' } });
  expect(onChange).toHaveBeenLastCalledWith(['5', '', '', '', '', '']);
  fireEvent.change(cells()[0], { target: { value: '83' } });
  expect(onChange).toHaveBeenLastCalledWith(['8', '', '', '', '', '']);
});

test('disabled — ячейки недоступны', () => {
  const { cells } = setup({ disabled: true });
  cells().forEach((c) => expect(c).toBeDisabled());
});

test('ошибка: aria-invalid и aria-describedby только при error', () => {
  const { cells, rerender, onChange } = setup({ describedBy: 'code-err' });
  cells().forEach((c) => {
    expect(c).not.toHaveAttribute('aria-invalid');
    expect(c).not.toHaveAttribute('aria-describedby');
  });
  rerender(<CodeInput value={EMPTY} onChange={onChange} error describedBy="code-err" />);
  cells().forEach((c) => {
    expect(c).toHaveAttribute('aria-invalid', 'true');
    expect(c).toHaveAttribute('aria-describedby', 'code-err');
  });
});

test('ref.focus() ставит фокус на первую ячейку', () => {
  const ref = createRef();
  const { cells } = setup({ ref });
  cells()[4].focus();
  ref.current.focus();
  expect(cells()[0]).toHaveFocus();
});

test('Backspace в пустой ячейке стирает предыдущую', () => {
  const { cells, onChange } = setup({ value: ['1', '2', '', '', '', ''] });
  fireEvent.keyDown(cells()[2], { key: 'Backspace' });
  expect(onChange).toHaveBeenLastCalledWith(['1', '', '', '', '', '']);
  expect(cells()[1]).toHaveFocus();
});
