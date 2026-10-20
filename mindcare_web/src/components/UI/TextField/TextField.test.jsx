import fs from 'fs';
import path from 'path';
import { createRef } from 'react';
import { render, screen } from '@testing-library/react';
import TextField from './TextField';

test('label связан с input; доступное имя по подписи', () => {
  render(<TextField label="ФИО" value="Иван" onChange={() => {}} />);
  expect(screen.getByLabelText('ФИО')).toHaveValue('Иван');
});

test('подсказка и ошибка описывают поле, ошибка объявляется и помечает aria-invalid', () => {
  render(<TextField label="Email" hint="Для связи" error="Введите корректный email" onChange={() => {}} value="" />);
  const input = screen.getByLabelText('Email');
  expect(input).toHaveAttribute('aria-invalid', 'true');
  const alert = screen.getByRole('alert');
  expect(alert).toHaveTextContent('Введите корректный email');
  expect(input.getAttribute('aria-describedby').split(' ')).toEqual(
    expect.arrayContaining([alert.id, screen.getByText('Для связи').id]),
  );
});

test('без ошибки нет aria-invalid и role=alert', () => {
  render(<TextField label="Поле" value="" onChange={() => {}} />);
  expect(screen.getByLabelText('Поле')).not.toHaveAttribute('aria-invalid');
  expect(screen.queryByRole('alert')).toBeNull();
});

test('ref указывает на input, readOnly/maxLength передаются', () => {
  const ref = createRef();
  render(<TextField ref={ref} label="Email аккаунта" value="a@b.ru" readOnly maxLength={50} onChange={() => {}} />);
  expect(ref.current).toBe(screen.getByLabelText('Email аккаунта'));
  expect(ref.current).toHaveAttribute('readonly');
  expect(ref.current).toHaveAttribute('maxlength', '50');
});

describe('TextField appearance', () => {
  it('по умолчанию вид прежний', () => {
    render(<TextField label="Поле" value="" onChange={() => {}} />);
    expect(screen.getByLabelText('Поле').className).not.toMatch(/inputField/);
    expect(screen.getByText('Поле').className).not.toMatch(/labelField/);
  });

  it('appearance="field" включает общую со Select коробку', () => {
    render(<TextField appearance="field" label="Поле" value="" onChange={() => {}} />);
    expect(screen.getByLabelText('Поле').className).toMatch(/inputField/);
    expect(screen.getByText('Поле').className).toMatch(/labelField/);
  });

  it('appearance="field" не меняет связи label/hint/error', () => {
    render(
      <TextField appearance="field" label="Поле" hint="Подсказка" error="Ошибка" value="" onChange={() => {}} />,
    );
    const input = screen.getByLabelText('Поле');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription('Подсказка Ошибка');
  });
});

// Поверхность поля — правило CSS (jsdom не применяет CSS Modules).
describe('TextField.module.css: поверхность', () => {
  const css = fs.readFileSync(path.join(__dirname, 'TextField.module.css'), 'utf8');
  const block = (selector) => {
    const start = css.indexOf(`${selector} {`);
    expect(start).toBeGreaterThanOrEqual(0);
    return css.slice(start, css.indexOf('}', start));
  };

  test('редактируемое поле — светлая поверхность и рамка --outline', () => {
    expect(block('.input')).toMatch(/background:\s*var\(--surface\);/);
    expect(block('.input')).toMatch(/border:\s*1px solid var\(--outline\)/);
  });

  test('поле только для чтения — контейнерный фон', () => {
    expect(block('.input[readonly]')).toMatch(/background:\s*var\(--surface-container\)/);
  });

  test('focus state прежний: focus ring и рамка --primary', () => {
    expect(block('.input:focus-visible')).toMatch(/outline:\s*var\(--focus-ring-width\) solid var\(--focus-ring-color\)/);
    expect(block('.input:focus-visible')).toMatch(/border-color:\s*var\(--primary\)/);
  });
});

test('readOnly поле остаётся readonly (вид — контейнерный фон)', () => {
  render(<TextField label="Email аккаунта" value="a@b.ru" readOnly onChange={() => {}} />);
  const input = screen.getByLabelText('Email аккаунта');
  expect(input).toHaveAttribute('readonly');
  expect(input).toHaveClass('input');
});
