import fs from 'fs';
import path from 'path';
import { fireEvent, render, screen } from '@testing-library/react';
import SocialEmailStep from './SocialEmailStep';

const MASKED = 'i***@donnu.ru';

function setup(over = {}) {
  const props = {
    maskedEmail: null,
    emailAllowed: false,
    error: '',
    loading: false,
    onSubmit: jest.fn(),
    onRestart: jest.fn(),
    ...over,
  };
  const utils = render(<SocialEmailStep {...props} />);
  return { props, ...utils };
}

const field = () => screen.getByLabelText('Электронная почта');

// ── адрес провайдера есть и разрешён ────────────────────────────────────────

test('адрес есть и разрешён: маска только для чтения, «Продолжить» → onSubmit(null)', () => {
  const { props } = setup({ maskedEmail: MASKED, emailAllowed: true });
  expect(screen.getByRole('heading', { name: 'Почта для регистрации' })).toBeInTheDocument();
  expect(screen.getByText('Код подтверждения будет отправлен на этот адрес.')).toBeInTheDocument();
  expect(field()).toHaveValue(MASKED);
  expect(field()).toHaveAttribute('readonly');
  expect(screen.queryByRole('button', { name: 'Получить код' })).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
  expect(props.onSubmit).toHaveBeenCalledTimes(1);
  expect(props.onSubmit).toHaveBeenCalledWith(null);          // адрес backend берёт из ticket
});

test('«Нет доступа к этой почте? Указать другую» открывает редактируемое поле', () => {
  const { props } = setup({ maskedEmail: MASKED, emailAllowed: true });
  fireEvent.click(screen.getByRole('button', {
    name: 'Нет доступа к этой почте? Указать другую',
  }));

  expect(field()).toHaveValue('');
  expect(field()).not.toHaveAttribute('readonly');
  expect(screen.getByText('Укажите электронную почту. Мы отправим на неё код подтверждения.'))
    .toBeInTheDocument();
  fireEvent.change(field(), { target: { value: '  new.address@donnu.ru ' } });
  fireEvent.click(screen.getByRole('button', { name: 'Получить код' }));
  expect(props.onSubmit).toHaveBeenCalledWith('new.address@donnu.ru');   // trim

  // Можно вернуться к показанному адресу.
  fireEvent.click(screen.getByRole('button', { name: `Использовать ${MASKED}` }));
  expect(field()).toHaveValue(MASKED);
  expect(field()).toHaveAttribute('readonly');
});

// ── адреса нет ───────────────────────────────────────────────────────────────

test('адреса нет: сразу редактируемое поле и «Получить код»', () => {
  const { props } = setup();
  expect(screen.getByRole('heading', { name: 'Почта для регистрации' })).toBeInTheDocument();
  expect(screen.getByText('Укажите электронную почту. Мы отправим на неё код подтверждения.'))
    .toBeInTheDocument();
  expect(field()).toHaveValue('');
  expect(field()).not.toHaveAttribute('readonly');
  expect(field()).toHaveAttribute('placeholder', 'example@donnu.ru');
  expect(screen.queryByRole('button', { name: 'Продолжить' })).toBeNull();
  expect(screen.queryByRole('button', { name: /Указать другую/ })).toBeNull();
  expect(screen.queryByRole('button', { name: /Использовать/ })).toBeNull();

  fireEvent.change(field(), { target: { value: 'student@donnu.ru' } });
  fireEvent.click(screen.getByRole('button', { name: 'Получить код' }));
  expect(props.onSubmit).toHaveBeenCalledWith('student@donnu.ru');
});

test.each(['', '   ', 'no-at-sign', 'a@b', 'a b@donnu.ru', '@donnu.ru'])(
  'некорректный формат %p → подсказка, onSubmit не вызывается',
  (value) => {
    const { props } = setup();
    fireEvent.change(field(), { target: { value } });
    fireEvent.click(screen.getByRole('button', { name: 'Получить код' }));
    expect(props.onSubmit).not.toHaveBeenCalled();
    expect(field()).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Введите корректный адрес электронной почты')).toBeInTheDocument();
  },
);

test('подсказка формата исчезает при правке, Enter отправляет форму', () => {
  const { props } = setup();
  fireEvent.click(screen.getByRole('button', { name: 'Получить код' }));
  expect(field()).toHaveAttribute('aria-invalid', 'true');
  fireEvent.change(field(), { target: { value: 'ok@donnu.ru' } });
  expect(field()).not.toHaveAttribute('aria-invalid');
  fireEvent.submit(field());
  expect(props.onSubmit).toHaveBeenCalledWith('ok@donnu.ru');
});

// ── адрес провайдера вне разрешённых доменов ────────────────────────────────

test('адрес есть, но домен не разрешён: продолжить с ним нельзя — только ввод другого', () => {
  const { props } = setup({ maskedEmail: 'i***@vk.ru', emailAllowed: false });
  expect(screen.getByText('Для регистрации укажите почту разрешённого домена.'))
    .toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Продолжить' })).toBeNull();
  expect(screen.queryByRole('button', { name: /Использовать/ })).toBeNull();
  expect(field()).toHaveValue('');
  expect(field()).not.toHaveAttribute('readonly');

  fireEvent.change(field(), { target: { value: 'student@donnu.ru' } });
  fireEvent.click(screen.getByRole('button', { name: 'Получить код' }));
  expect(props.onSubmit).toHaveBeenCalledWith('student@donnu.ru');
});

// ── ошибки и загрузка ────────────────────────────────────────────────────────

test.each([
  'Аккаунт с таким email уже существует. Войдите по email и паролю.',
  'Регистрация доступна только для разрешённых почтовых доменов.',
])('ошибка от backend (%s) показана внутри шага, ввод можно повторить', (error) => {
  const { props, rerender } = setup({ error: '' });
  fireEvent.change(field(), { target: { value: 'taken@donnu.ru' } });
  rerender(<SocialEmailStep {...props} error={error} />);

  expect(screen.getByText(error)).toHaveAttribute('role', 'alert');
  expect(screen.getByText(error)).toHaveClass('apiError');          // общий стиль ошибок форм
  expect(field()).toHaveValue('taken@donnu.ru');                      // ввод сохранён
  fireEvent.change(field(), { target: { value: 'other@donnu.ru' } });
  fireEvent.click(screen.getByRole('button', { name: 'Получить код' }));
  expect(props.onSubmit).toHaveBeenCalledWith('other@donnu.ru');
});

test('ошибка показывается и в режиме «адрес провайдера»', () => {
  setup({ maskedEmail: MASKED, emailAllowed: true, error: 'Слишком много попыток.' });
  expect(screen.getByText('Слишком много попыток.')).toHaveAttribute('role', 'alert');
});

test('во время отправки кнопка «Получить код» заблокирована', () => {
  setup({ loading: true });
  expect(screen.getByRole('button', { name: 'Отправляем код…' })).toBeDisabled();
});

test('в режиме адреса провайдера загрузка блокирует «Продолжить» и «Указать другую»', () => {
  setup({ maskedEmail: MASKED, emailAllowed: true, loading: true });
  expect(screen.getByRole('button', { name: 'Отправляем код…' })).toBeDisabled();
  expect(screen.getByRole('button', { name: /Указать другую/ })).toBeDisabled();
});

test('«Начать заново» вызывает onRestart в обоих режимах', () => {
  const first = setup();
  fireEvent.click(screen.getByRole('button', { name: 'Начать заново' }));
  expect(first.props.onRestart).toHaveBeenCalledTimes(1);
  first.unmount();

  const second = setup({ maskedEmail: MASKED, emailAllowed: true });
  fireEvent.click(screen.getByRole('button', { name: 'Начать заново' }));
  expect(second.props.onRestart).toHaveBeenCalledTimes(1);
});

test('нет полей имени, пароля, кода и вкладок', () => {
  setup();
  expect(screen.queryByLabelText('Имя')).toBeNull();
  expect(screen.queryByLabelText(/Пароль/)).toBeNull();
  expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.queryByRole('checkbox')).toBeNull();                  // согласие — на шаге кода
  expect(screen.getAllByRole('textbox')).toHaveLength(1);
});

// ── тексты и оформление ──────────────────────────────────────────────────────

const VIEWS = [
  ['адреса нет', {}],
  ['адрес разрешён', { maskedEmail: MASKED, emailAllowed: true }],
  ['домен не разрешён', { maskedEmail: 'i***@vk.ru', emailAllowed: false }],
  ['ошибка backend', { error: 'Регистрация доступна только для разрешённых почтовых доменов.' }],
];

test.each(VIEWS)('тексты (%s): без длинного тире, стрелок, «EMAIL» и упоминания провайдера', (_, over) => {
  const { container } = setup(over);
  const text = container.textContent;
  expect(text).not.toMatch(/[—–←→]/);
  expect(text).not.toMatch(/EMAIL|Email/);
  expect(text).not.toMatch(/VK|Яндекс|подтверждён|ticket|OAuth|allowlist/i);
  // Подпись поля — обычным регистром и по-русски.
  expect(screen.getByText('Электронная почта').tagName).toBe('LABEL');
});

test.each(VIEWS)('оформление (%s): только общие классы AuthModal, без inline-стилей', (_, over) => {
  const { container } = setup(over);
  // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access
  expect(container.querySelectorAll('[style]')).toHaveLength(0);
  // eslint-disable-next-line testing-library/no-node-access
  const root = container.firstChild;
  expect(root).toHaveClass('authPanel', 'active');                    // как у форм входа/регистрации
  expect(screen.getByRole('heading', { name: 'Почта для регистрации' })).toHaveClass('stepTitle');
  // eslint-disable-next-line testing-library/no-node-access
  const fieldWrap = field().parentElement;
  expect(fieldWrap).toHaveClass('authField', 'plainLabel');           // общий стиль поля, подпись без uppercase
  expect(screen.getByRole('button', { name: /Получить код|Продолжить/ })).toHaveClass('authBtn');
  expect(screen.getByRole('button', { name: 'Начать заново' })).toHaveClass('ghost', 'ghostMuted');
});

describe('стили шага — общие стили AuthModal', () => {
  const read = (...parts) => fs.readFileSync(path.join(__dirname, ...parts), 'utf8');
  const rule = (css, selector) => {
    const start = css.indexOf(`${selector} {`);
    expect(start).toBeGreaterThanOrEqual(0);
    return css.slice(start, css.indexOf('}', start));
  };

  test('шаг не задаёт свой шрифт и не подключает свой CSS', () => {
    const source = read('SocialEmailStep.jsx');
    expect(source).not.toMatch(/font-?family/i);
    expect(source).not.toMatch(/style=/);
    const imports = source.match(/^import .*$/gm);
    expect(imports.filter((line) => /\.css'/.test(line))).toEqual([
      "import styles from './AuthModal.module.css';",
    ]);
  });

  test('заголовок шага наследует шрифт модалки, а не глобальный serif для h2', () => {
    const title = rule(read('AuthModal.module.css'), '.stepTitle');
    // Единственное объявление шрифта — наследование.
    expect(title.match(/font-family:[^;]+;/g)).toEqual(['font-family: inherit;']);
  });

  test('подпись поля шага — без uppercase', () => {
    const label = rule(read('AuthModal.module.css'), '.authField.plainLabel label');
    expect(label).toMatch(/text-transform:\s*none;/);
  });
});
