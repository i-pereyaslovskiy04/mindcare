import { act, fireEvent, render, screen } from '@testing-library/react';
import RegistrationOtpStep, { EMPTY_CODE } from './RegistrationOtpStep';

const FULL = ['1', '2', '3', '4', '5', '6'];

function setup(over = {}) {
  const props = {
    email: 'student@donnu.ru',
    code: EMPTY_CODE,
    onCodeChange: jest.fn(),
    error: '',
    timer: 42,
    onResend: jest.fn(),
    onConfirm: jest.fn(),
    backLabel: '← Изменить данные',
    onBack: jest.fn(),
    ...over,
  };
  const utils = render(<RegistrationOtpStep {...props} />);
  return { props, ...utils };
}

beforeEach(() => { jest.useFakeTimers(); });
afterEach(() => { jest.useRealTimers(); });

test('заголовок, адрес, CodeInput, таймер, кнопки; без вкладок и полей ввода данных', () => {
  setup();
  expect(screen.getByRole('heading', { name: 'Подтверждение регистрации' })).toBeInTheDocument();
  expect(screen.getByText('student@donnu.ru')).toBeInTheDocument();
  expect(screen.getByRole('group', { name: 'Код подтверждения' })).toBeInTheDocument();
  expect(screen.getByText(/Отправить повторно через/)).toHaveTextContent('42');
  expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '← Изменить данные' })).toBeInTheDocument();
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.queryByRole('checkbox')).toBeNull();          // согласие — только по запросу
  expect(screen.queryByLabelText('Имя')).toBeNull();
  expect(screen.queryByLabelText(/Пароль/)).toBeNull();
});

test('таймер истёк → «Отправить повторно» вызывает onResend', () => {
  const { props } = setup({ timer: 0 });
  fireEvent.click(screen.getByRole('button', { name: 'Отправить повторно' }));
  expect(props.onResend).toHaveBeenCalledTimes(1);
});

test('6 цифр → авто-подтверждение один раз', () => {
  const { props } = setup({ code: FULL });
  act(() => { jest.advanceTimersByTime(200); });
  expect(props.onConfirm).toHaveBeenCalledTimes(1);
  expect(props.onConfirm).toHaveBeenCalledWith(FULL);
});

test('с чекбоксом согласия: без согласия нет авто-подтверждения, кнопка показывает подсказку', () => {
  const consent = { checked: false, error: false, onChange: jest.fn(), onMissing: jest.fn() };
  const { props } = setup({ code: FULL, consent });
  act(() => { jest.advanceTimersByTime(200); });
  expect(props.onConfirm).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
  expect(consent.onMissing).toHaveBeenCalledTimes(1);
  expect(props.onConfirm).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('checkbox'));
  expect(consent.onChange.mock.calls[0][0]).toBe(true);
});

test('согласие отмечено → авто-подтверждение', () => {
  const consent = { checked: true, error: false, onChange: jest.fn(), onMissing: jest.fn() };
  const { props } = setup({ code: FULL, consent });
  act(() => { jest.advanceTimersByTime(200); });
  expect(props.onConfirm).toHaveBeenCalledTimes(1);
});

test('blocked: нет повторной отправки и подтверждения, ошибка видна', () => {
  const { props } = setup({ code: FULL, blocked: true, error: 'Отказ', timer: 0 });
  act(() => { jest.advanceTimersByTime(200); });
  expect(props.onConfirm).not.toHaveBeenCalled();
  expect(screen.queryByText(/Отправить повторно/)).toBeNull();
  expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
  expect(screen.getByRole('alert')).toHaveTextContent('Отказ');
});

test('ссылка назад вызывает onBack', () => {
  const { props } = setup({ backLabel: '← Начать заново' });
  fireEvent.click(screen.getByRole('button', { name: '← Начать заново' }));
  expect(props.onBack).toHaveBeenCalledTimes(1);
});
