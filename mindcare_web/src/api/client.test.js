import { parseErrorMessage } from './client';

describe('parseErrorMessage', () => {
  test('detail-строка используется как сообщение', () => {
    expect(parseErrorMessage({ detail: 'Email уже зарегистрирован' }, 409))
      .toBe('Email уже зарегистрирован');
  });

  test('detail-массив из одного элемента → его msg', () => {
    expect(parseErrorMessage({ detail: [{ msg: 'Field required' }] }, 422))
      .toBe('Field required');
  });

  test('detail-массив из нескольких → оба сообщения через "; "', () => {
    const msg = parseErrorMessage({ detail: [{ msg: 'A' }, { msg: 'B' }] }, 422);
    expect(msg).toContain('A');
    expect(msg).toContain('B');
    expect(msg).toBe('A; B');
  });

  test('detail c loc → читаемое поле перед msg (без префикса body)', () => {
    expect(parseErrorMessage({ detail: [{ loc: ['body', 'email'], msg: 'Invalid' }] }, 422))
      .toBe('email: Invalid');
  });

  test('никогда не превращается в "[object Object]"', () => {
    const msg = parseErrorMessage({ detail: [{ type: 'x', loc: ['body', 'a'], msg: 'нужно', input: null }] }, 422);
    expect(msg).not.toContain('[object Object]');
  });

  test('message-строка как fallback при отсутствии detail', () => {
    expect(parseErrorMessage({ message: 'Что-то пошло не так' }, 500))
      .toBe('Что-то пошло не так');
  });

  test('неизвестный формат → HTTP <status>', () => {
    expect(parseErrorMessage({}, 503)).toBe('HTTP 503');
  });

  test('пустое тело без статуса → общий fallback', () => {
    expect(parseErrorMessage({}, undefined)).toBe('Ошибка запроса');
  });
});
