import fs from 'fs';
import path from 'path';
import { render, screen, fireEvent } from '@testing-library/react';
import Select from './Select';

const OPTIONS = [
  { value: 'a', label: 'Первый' },
  { value: 'b', label: 'Второй' },
];

describe('Select', () => {
  it('без error не добавляет aria-invalid/aria-describedby (прежнее поведение)', () => {
    render(<Select label="Тип" value="a" options={OPTIONS} onChange={jest.fn()} />);
    const control = screen.getByRole('button', { name: /Тип/ });
    expect(control).not.toHaveAttribute('aria-invalid');
    expect(control).not.toHaveAttribute('aria-describedby');
  });

  it('переданный id получает кнопка-контрол (цель фокуса)', () => {
    render(<Select id="my-select" label="Тип" options={OPTIONS} onChange={jest.fn()} />);
    expect(screen.getByRole('button', { name: /Тип/ })).toHaveAttribute('id', 'my-select');
  });

  it('без id контрол всё равно получает уникальный id', () => {
    render(
      <>
        <Select label="Первый" options={OPTIONS} onChange={jest.fn()} />
        <Select label="Второй" options={OPTIONS} onChange={jest.fn()} />
      </>,
    );
    const [first, second] = screen.getAllByRole('button');
    expect(first.id).toBeTruthy();
    expect(first.id).not.toBe(second.id);
  });

  it('ошибка связана с контролом: aria-invalid и aria-describedby на её id', () => {
    render(
      <Select id="svc" label="Сервис" options={OPTIONS} error="Выберите сервис" onChange={jest.fn()} />,
    );
    const control = screen.getByRole('button', { name: /Сервис/ });
    const alert = screen.getByRole('alert');
    expect(control).toHaveAttribute('aria-invalid', 'true');
    expect(control).toHaveAttribute('aria-describedby', alert.id);
    expect(alert.id).toBe('svc-error');
    expect(control).toHaveAccessibleDescription('Выберите сервис');
  });

  it('выбор варианта по-прежнему вызывает onChange', () => {
    const onChange = jest.fn();
    render(<Select label="Тип" options={OPTIONS} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /Тип/ }));
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Второй' }));
    expect(onChange).toHaveBeenCalledWith('b');
  });
});

describe('Select appearance', () => {
  it('по умолчанию — прежний вид: модификаторов field нет', () => {
    render(<Select label="Тип" error="Ошибка" options={OPTIONS} onChange={jest.fn()} />);
    expect(screen.getByRole('button', { name: /Тип/ }).className).not.toMatch(/controlField/);
    expect(screen.getByText('Тип').className).not.toMatch(/labelField/);
    expect(screen.getByRole('alert').className).not.toMatch(/errorField/);
  });

  it('appearance="field" включает вид TextField для подписи, контрола и ошибки', () => {
    render(
      <Select appearance="field" label="Тип" error="Ошибка" options={OPTIONS} onChange={jest.fn()} />,
    );
    expect(screen.getByRole('button', { name: /Тип/ }).className).toMatch(/controlField/);
    expect(screen.getByText('Тип').className).toMatch(/labelField/);
    expect(screen.getByRole('alert').className).toMatch(/errorField/);
  });

  it('appearance="field" не меняет поведение: выбор, aria, отключение', () => {
    const onChange = jest.fn();
    const { rerender } = render(
      <Select appearance="field" id="m" label="Тип" options={OPTIONS} onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Тип/ }));
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Первый' }));
    expect(onChange).toHaveBeenCalledWith('a');
    rerender(<Select appearance="field" id="m" label="Тип" options={OPTIONS} onChange={onChange} disabled />);
    expect(screen.getByRole('button', { name: /Тип/ })).toBeDisabled();
  });
});

describe('Select.module.css: поверхность appearance="field"', () => {
  const css = fs.readFileSync(path.join(__dirname, 'Select.module.css'), 'utf8');
  const block = (selector) => {
    const start = css.indexOf(`${selector} {`);
    expect(start).toBeGreaterThanOrEqual(0);
    return css.slice(start, css.indexOf('}', start));
  };

  test('field — светлая поверхность, рамка --outline', () => {
    expect(block('.control.controlField')).toMatch(/background:\s*var\(--surface\);/);
    expect(block('.control.controlField')).toMatch(/border:\s*1px solid var\(--outline\)/);
  });

  test('обычный Select не изменился', () => {
    expect(block('.control')).toMatch(/background:\s*var\(--warm-white\)/);
  });
});
