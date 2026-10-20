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
