import { act, fireEvent, render, screen, within } from '@testing-library/react';
import RegistrationOtpStep, { EMPTY_CODE, OTP_STATUS } from './RegistrationOtpStep';

const FULL = ['1', '2', '3', '4', '5', '6'];

function setup(over = {}) {
  const props = {
    description: 'Отправили 6-значный код на student@donnu.ru',
    code: EMPTY_CODE,
    onCodeChange: jest.fn(),
    error: '',
    resend: { secondsLeft: 42, onResend: jest.fn() },
    onConfirm: jest.fn(),
    secondaryAction: { label: '← Изменить данные', onClick: jest.fn() },
    ...over,
  };
  const utils = render(<RegistrationOtpStep {...props} />);
  return { props, ...utils };
}

const cells = () => within(screen.getByRole('group', { name: 'Код подтверждения' })).getAllByRole('textbox');
const flush = (ms = 200) => act(() => { jest.advanceTimersByTime(ms); });

beforeEach(() => { jest.useFakeTimers(); });
afterEach(() => { jest.useRealTimers(); });

test('заголовок, описание, CodeInput, таймер, кнопки; без вкладок и полей ввода данных', () => {
  setup();
  expect(screen.getByRole('heading', { name: 'Подтверждение регистрации' })).toBeInTheDocument();
  expect(screen.getByText('Отправили 6-значный код на student@donnu.ru')).toBeInTheDocument();
  expect(cells()).toHaveLength(6);
  expect(screen.getByText(/Отправить повторно через/)).toHaveTextContent('42');
  expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '← Изменить данные' })).toBeInTheDocument();
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.queryByRole('checkbox')).toBeNull();          // согласие — только по запросу
  expect(screen.queryByLabelText('Email')).toBeNull();
  expect(screen.queryByLabelText(/Пароль/)).toBeNull();
});

test('без resend и secondaryAction — ни таймера, ни лишних кнопок', () => {
  setup({ resend: undefined, secondaryAction: undefined });
  expect(screen.queryByText(/Отправить повторно/)).toBeNull();
  expect(screen.getAllByRole('button')).toHaveLength(1);       // только «Подтвердить»
});

test('таймер истёк → «Отправить повторно» вызывает onResend', () => {
  const onResend = jest.fn();
  setup({ resend: { secondsLeft: 0, onResend } });
  fireEvent.click(screen.getByRole('button', { name: 'Отправить повторно' }));
  expect(onResend).toHaveBeenCalledTimes(1);
});

test('6 цифр → авто-подтверждение один раз', () => {
  const { props } = setup({ code: FULL });
  flush();
  expect(props.onConfirm).toHaveBeenCalledTimes(1);
  expect(props.onConfirm).toHaveBeenCalledWith(FULL);
});

test('двойное подтверждение: авто, Enter и кнопка до ответа владельца → один вызов', () => {
  const { props } = setup({ code: FULL });
  fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
  fireEvent.submit(screen.getByRole('form', { name: 'Подтверждение регистрации' }));
  flush();
  fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
  expect(props.onConfirm).toHaveBeenCalledTimes(1);
});

test('после ответа владельца (submitting → ready, новый код) подтвердить можно снова', () => {
  const { props, rerender } = setup({ code: FULL });
  flush();
  const other = ['6', '5', '4', '3', '2', '1'];
  rerender(<RegistrationOtpStep {...props} code={FULL} status={OTP_STATUS.SUBMITTING} />);
  rerender(<RegistrationOtpStep {...props} code={EMPTY_CODE} status={OTP_STATUS.READY} error="Неверный код" />);
  rerender(<RegistrationOtpStep {...props} code={other} status={OTP_STATUS.READY} />);
  flush();
  expect(props.onConfirm).toHaveBeenCalledTimes(2);
  expect(props.onConfirm).toHaveBeenLastCalledWith(other);
});

test('submitting: ячейки недоступны, «Проверяем…», вторичное действие недоступно', () => {
  const { props } = setup({ code: FULL, status: OTP_STATUS.SUBMITTING });
  flush();
  expect(props.onConfirm).not.toHaveBeenCalled();
  cells().forEach((cell) => expect(cell).toBeDisabled());
  expect(screen.getByRole('button', { name: 'Проверяем…' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '← Изменить данные' })).toBeDisabled();
});

test('blocked: нет повторной отправки и подтверждения, ячейки недоступны, ошибка видна', () => {
  const { props } = setup({
    code: FULL, status: OTP_STATUS.BLOCKED, error: 'Отказ',
    resend: { secondsLeft: 0, onResend: jest.fn() },
  });
  flush();
  expect(props.onConfirm).not.toHaveBeenCalled();
  expect(screen.queryByText(/Отправить повторно/)).toBeNull();
  expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
  cells().forEach((cell) => expect(cell).toBeDisabled());
  expect(screen.getByRole('alert')).toHaveTextContent('Отказ');
  // «Начать заново» остаётся единственным выходом.
  expect(screen.getByRole('button', { name: '← Изменить данные' })).toBeEnabled();
});

test('ошибка объявляется и связана с ячейками', () => {
  setup({ error: 'Неверный код. Осталось попыток: 4' });
  const alert = screen.getByRole('alert');
  expect(alert).toHaveTextContent('Неверный код. Осталось попыток: 4');
  cells().forEach((cell) => {
    expect(cell).toHaveAttribute('aria-invalid', 'true');
    expect(cell).toHaveAttribute('aria-describedby', alert.id);
  });
});

test('фокус на первой ячейке при открытии шага', () => {
  setup();
  expect(cells()[0]).toHaveFocus();
  flush(100);                                   // после кадра модалки — тоже
  expect(cells()[0]).toHaveFocus();
});

test('после ошибки с очищенным кодом фокус возвращается на первую ячейку', () => {
  const { props, rerender } = setup({ code: FULL });
  flush();
  cells()[5].focus();
  rerender(<RegistrationOtpStep {...props} code={FULL} status={OTP_STATUS.SUBMITTING} />);
  rerender(<RegistrationOtpStep {...props} code={EMPTY_CODE} error="Неверный код" />);
  expect(cells()[0]).toHaveFocus();
});

test('с чекбоксом согласия: без согласия нет авто-подтверждения, кнопка показывает подсказку', () => {
  const consent = { checked: false, error: false, onChange: jest.fn(), onMissing: jest.fn() };
  const { props } = setup({ code: FULL, consent });
  flush();
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
  flush();
  expect(props.onConfirm).toHaveBeenCalledTimes(1);
});

test('вторичное действие вызывает свой обработчик', () => {
  const onClick = jest.fn();
  setup({ secondaryAction: { label: 'Начать заново', onClick } });
  fireEvent.click(screen.getByRole('button', { name: 'Начать заново' }));
  expect(onClick).toHaveBeenCalledTimes(1);
});

test('ссылка на политику открывается в новой вкладке: шаг кода и ticket в памяти не теряются', () => {
  const consent = { checked: false, error: false, onChange: jest.fn(), onMissing: jest.fn() };
  const { props } = setup({ consent });

  const link = screen.getByRole('link', { name: 'политикой персональных данных' });
  expect(link).toHaveAttribute('href', '/privacy-policy');            // адрес и текст прежние
  expect(link).toHaveAttribute('target', '_blank');
  expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  expect(screen.getAllByRole('link')).toHaveLength(1);                // других ссылок на шаге нет

  // Клик по ссылке — не отметка согласия и не подтверждение кода.
  fireEvent.click(link);
  expect(consent.onChange).not.toHaveBeenCalled();
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(props.onConfirm).not.toHaveBeenCalled();
});

test('без согласия (обычная регистрация) ссылок на шаге кода нет', () => {
  setup();
  expect(screen.queryByRole('link')).toBeNull();
});
