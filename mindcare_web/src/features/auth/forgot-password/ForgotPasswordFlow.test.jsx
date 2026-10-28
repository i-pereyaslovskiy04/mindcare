import fs from 'fs';
import path from 'path';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ForgotPasswordModal from './ForgotPasswordModal';
import { passwordResetConfirm, passwordResetInit } from '../../../api/auth.api';

// Без заглушки OTPInput: настоящий CodeInput — фокус на ячейке, автоотправка
// и возврат с шага 3 проверяются на реальном компоненте.
jest.mock('../../../api/auth.api');

const EMAIL = 'me@example.org';
const dialog = () => screen.getByRole('dialog', { name: 'Восстановление пароля' });
const heading = () => within(dialog()).getByRole('heading', { level: 2 });
const wait = (ms) => act(async () => { await new Promise((r) => { setTimeout(r, ms); }); });

function renderModal(props = {}) {
  const onClose = jest.fn();
  render(<ForgotPasswordModal open onClose={onClose} {...props} />);
  return { onClose };
}

async function toCodeStep() {
  userEvent.type(screen.getByLabelText('Электронная почта'), `${EMAIL}{enter}`);
  await screen.findByRole('heading', { name: /Введите код/ });
}

async function toPasswordStep() {
  await toCodeStep();
  fireEvent.paste(screen.getByLabelText('Цифра 1'), {
    clipboardData: { getData: () => '123456' },
  });
  await screen.findByLabelText('Новый пароль');
}

beforeEach(() => {
  passwordResetInit.mockResolvedValue({});
  passwordResetConfirm.mockResolvedValue({});
});

// ── формы и Enter ────────────────────────────────────────────────────────────

describe('формы шагов', () => {
  it('каждый интерактивный шаг — <form> с submit-кнопкой', async () => {
    renderModal();
    // eslint-disable-next-line testing-library/no-node-access
    expect(screen.getByLabelText('Электронная почта').form).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Отправить код' })).toHaveAttribute('type', 'submit');

    await toCodeStep();
    // eslint-disable-next-line testing-library/no-node-access
    expect(screen.getByLabelText('Цифра 1').form).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toHaveAttribute('type', 'submit');
    expect(screen.getByRole('button', { name: '← Изменить почту' })).toHaveAttribute('type', 'button');

    fireEvent.paste(screen.getByLabelText('Цифра 1'), { clipboardData: { getData: () => '123456' } });
    const pass = await screen.findByLabelText('Новый пароль');
    // eslint-disable-next-line testing-library/no-node-access
    expect(pass.form).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Сохранить пароль' })).toHaveAttribute('type', 'submit');
    expect(screen.getByRole('button', { name: '← Изменить код' })).toHaveAttribute('type', 'button');
  });

  it('Enter в поле email отправляет только шаг 1', async () => {
    renderModal();
    userEvent.type(screen.getByLabelText('Электронная почта'), `${EMAIL}{enter}`);
    await screen.findByRole('heading', { name: /Введите код/ });
    expect(passwordResetInit).toHaveBeenCalledTimes(1);
    expect(passwordResetInit).toHaveBeenCalledWith({ email: EMAIL });
    expect(passwordResetConfirm).not.toHaveBeenCalled();
  });

  it('Enter на «Закрыть» закрывает окно и не отправляет шаг', async () => {
    const { onClose } = renderModal();
    userEvent.type(screen.getByLabelText('Электронная почта'), EMAIL);
    userEvent.type(screen.getByRole('button', { name: 'Закрыть' }), '{enter}');
    expect(onClose).toHaveBeenCalled();
    await wait(50);
    expect(passwordResetInit).not.toHaveBeenCalled();
  });

  it('Enter на «Изменить код» только возвращает к коду: пароль не отправляется', async () => {
    renderModal();
    await toPasswordStep();
    userEvent.type(screen.getByLabelText('Новый пароль'), 'new-password-1');
    userEvent.type(screen.getByLabelText('Повторите пароль'), 'new-password-1');
    userEvent.type(screen.getByRole('button', { name: '← Изменить код' }), '{enter}');
    expect(heading()).toHaveTextContent('Введите код');
    await wait(400);
    expect(heading()).toHaveTextContent('Введите код');
    expect(passwordResetConfirm).not.toHaveBeenCalled();
  });

  it('Enter на «Изменить почту» только возвращает к email: код не отправляется', async () => {
    renderModal();
    await toCodeStep();
    userEvent.type(screen.getByRole('button', { name: '← Изменить почту' }), '{enter}');
    expect(heading()).toHaveTextContent('Восстановление пароля');
    expect(screen.queryByLabelText('Новый пароль')).toBeNull();
  });
});

// ── возврат с шага 3 (регрессия: автоотправка уводила обратно) ──────────────

describe('«← Изменить код»', () => {
  it('оставляет на шаге 2: прежний код не отправляется повторно', async () => {
    renderModal();
    await toPasswordStep();
    userEvent.click(screen.getByRole('button', { name: '← Изменить код' }));

    expect(heading()).toHaveTextContent('Введите код');
    await wait(400);                                    // автоотправка была через 120 мс
    expect(heading()).toHaveTextContent('Введите код');
    expect(screen.queryByLabelText('Новый пароль')).toBeNull();
    // Код можно исправить — новый полный ввод снова ведёт на шаг 3.
    fireEvent.paste(screen.getByLabelText('Цифра 1'), { clipboardData: { getData: () => '654321' } });
    expect(await screen.findByLabelText('Новый пароль')).toBeInTheDocument();
  });

  it('неверный код с шага 3: остаётся шаг 2 с ошибкой, без автоматического возврата', async () => {
    passwordResetConfirm.mockRejectedValue(new Error('Неверный код'));
    renderModal();
    await toPasswordStep();
    userEvent.type(screen.getByLabelText('Новый пароль'), 'new-password-1');
    userEvent.type(screen.getByLabelText('Повторите пароль'), 'new-password-1{enter}');

    expect(await screen.findByText('Неверный код')).toHaveAttribute('role', 'alert');
    await wait(400);
    expect(heading()).toHaveTextContent('Введите код');
    expect(screen.getByText('Неверный код')).toBeInTheDocument();
    expect(passwordResetConfirm).toHaveBeenCalledTimes(1);
  });
});

// ── фокус ────────────────────────────────────────────────────────────────────

describe('фокус', () => {
  it('при открытии и смене шага — основное поле, а не «Закрыть»', async () => {
    renderModal();
    await waitFor(() => expect(screen.getByLabelText('Электронная почта')).toHaveFocus());

    await toCodeStep();
    await waitFor(() => expect(screen.getByLabelText('Цифра 1')).toHaveFocus());

    fireEvent.paste(screen.getByLabelText('Цифра 1'), { clipboardData: { getData: () => '123456' } });
    const pass = await screen.findByLabelText('Новый пароль');
    await waitFor(() => expect(pass).toHaveFocus());

    userEvent.click(screen.getByRole('button', { name: '← Изменить код' }));
    await waitFor(() => expect(screen.getByLabelText('Цифра 1')).toHaveFocus());
  });

  it('ошибка проверки email — фокус на поле, ошибка связана с ним', async () => {
    renderModal();
    const email = screen.getByLabelText('Электронная почта');
    userEvent.type(email, 'abc');
    userEvent.click(screen.getByRole('button', { name: 'Отправить код' }));
    await waitFor(() => expect(email).toHaveFocus());
    expect(email).toHaveAttribute('aria-invalid', 'true');
    expect(email).toHaveAccessibleDescription('Введите корректный email');
    expect(passwordResetInit).not.toHaveBeenCalled();
  });

  it('неполный код — фокус на первую ячейку', async () => {
    renderModal();
    await toCodeStep();
    userEvent.type(screen.getByLabelText('Цифра 1'), '12');
    userEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    expect(await screen.findByText('Введите все 6 цифр кода')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText('Цифра 1')).toHaveFocus());
    expect(screen.getByLabelText('Цифра 1')).toHaveAccessibleDescription('Введите все 6 цифр кода');
  });

  it('ошибки пароля — фокус на первое ошибочное поле', async () => {
    renderModal();
    await toPasswordStep();
    const pass = screen.getByLabelText('Новый пароль');
    const pass2 = screen.getByLabelText('Повторите пароль');

    userEvent.type(pass, 'new-password-1');
    userEvent.type(pass2, 'другое-значение');
    userEvent.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    await waitFor(() => expect(pass2).toHaveFocus());
    expect(pass2).toHaveAccessibleDescription('Пароли не совпадают');

    userEvent.clear(pass);
    userEvent.type(pass, 'abc');
    userEvent.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    await waitFor(() => expect(pass).toHaveFocus());
    expect(pass).toHaveAccessibleDescription('Минимум 8 символов');
    expect(passwordResetConfirm).not.toHaveBeenCalled();
  });
});

// ── доступность и семантика ─────────────────────────────────────────────────

describe('доступность', () => {
  it('прогресс «Шаг N из 3» для скринридера; заголовки шагов — h2', async () => {
    renderModal();
    expect(screen.getByText('Шаг 1 из 3')).toHaveClass('visually-hidden');
    expect(heading()).toHaveTextContent('Восстановление пароля');
    expect(within(dialog()).queryByRole('heading', { level: 1 })).toBeNull();

    await toCodeStep();
    expect(screen.getByText('Шаг 2 из 3')).toBeInTheDocument();
    expect(heading()).toHaveTextContent('Введите код');

    fireEvent.paste(screen.getByLabelText('Цифра 1'), { clipboardData: { getData: () => '123456' } });
    await screen.findByLabelText('Новый пароль');
    expect(screen.getByText('Шаг 3 из 3')).toBeInTheDocument();
    expect(heading()).toHaveTextContent('Новый пароль');
  });

  it('без ошибки у полей нет описаний: скрытые подсказки не привязаны', async () => {
    renderModal();
    expect(screen.getByLabelText('Электронная почта')).not.toHaveAttribute('aria-describedby');
    await toPasswordStep();
    expect(screen.getByLabelText('Новый пароль')).not.toHaveAttribute('aria-describedby');
    expect(screen.getByLabelText('Повторите пароль')).not.toHaveAttribute('aria-describedby');
    expect(screen.queryByText('Пароли не совпадают')).toBeNull();
    expect(screen.queryByText('Минимум 8 символов')).toBeNull();
  });

  it('шаг 3: autocomplete new-password и скрытое поле username с email сценария', async () => {
    renderModal();
    await toPasswordStep();
    expect(screen.getByLabelText('Новый пароль')).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByLabelText('Повторите пароль')).toHaveAttribute('autocomplete', 'new-password');
    const username = screen.getByDisplayValue(EMAIL);
    expect(username).toHaveAttribute('autocomplete', 'username');
    expect(username).not.toBeVisible();
    // eslint-disable-next-line testing-library/no-node-access
    expect(username.form).toBe(screen.getByLabelText('Новый пароль').form);
  });

  it('сила пароля: подпись в строке полосок и объявляется', async () => {
    renderModal();
    await toPasswordStep();
    userEvent.type(screen.getByLabelText('Новый пароль'), 'abc');
    const label = screen.getByText('Слабый');
    expect(label).toHaveAttribute('aria-live', 'polite');
  });
});

// ── CSS: регрессии раскладки (CSS-модули RTL не видит) ──────────────────────

describe('CSS восстановления пароля', () => {
  const css = fs.readFileSync(path.join(__dirname, 'styles', 'forgot-password.module.css'), 'utf8');
  const rule = (selector) => {
    const m = css.match(new RegExp(`(^|\\n)\\.${selector}\\s*\\{([^}]*)\\}`));
    return m ? m[2] : null;
  };

  it('нет конфликтующего .body: контейнер — .content, вводный текст — .lead без padding', () => {
    expect(rule('body')).toBeNull();
    expect(css.match(/(^|\n)\.content\s*\{/g)).toHaveLength(1);
    expect(rule('lead')).not.toMatch(/padding/);
  });

  it('скрытые подсказки и подпись силы не резервируют высоту', () => {
    expect(rule('hint')).not.toMatch(/min-height/);
    expect(css).not.toMatch(/visibility\s*:\s*hidden/);
    expect(rule('strengthLabel')).not.toMatch(/min-height/);
  });

  it('сила пароля — одна строка: полоски и подпись рядом', () => {
    const strength = rule('strength');
    expect(strength).toMatch(/display\s*:\s*flex/);
    expect(strength).not.toMatch(/flex-direction\s*:\s*column/);
  });

  it('текстовые действия — зона нажатия не меньше 44px', () => {
    expect(rule('ghost')).toMatch(/min-height\s*:\s*44px/);
  });
});
