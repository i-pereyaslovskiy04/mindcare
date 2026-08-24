import { fireEvent, render, screen } from '@testing-library/react';
import AuditPagination from './AuditPagination';
import { computePagination } from '../lib/auditFilters';

function setup(props) {
  const onPageChange = jest.fn();
  const { container } = render(
    <AuditPagination
      page={1}
      totalPages={5}
      windowLimited={false}
      maxResultWindow={100000}
      onPageChange={onPageChange}
      {...props}
    />,
  );
  return { onPageChange, container };
}

describe('видимость', () => {
  test('одна страница — пагинации нет', () => {
    const { container } = setup({ totalPages: 1 });
    expect(container).toBeEmptyDOMElement();
  });

  test('несколько страниц — есть обе кнопки и счётчик', () => {
    setup({ page: 2, totalPages: 5 });
    expect(screen.getByRole('button', { name: /Назад/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Вперёд/ })).toBeInTheDocument();
    expect(screen.getByText('Стр. 2 из 5')).toBeInTheDocument();
  });
});

describe('границы', () => {
  test('на первой странице «Назад» отключена', () => {
    setup({ page: 1, totalPages: 5 });
    expect(screen.getByRole('button', { name: /Назад/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Вперёд/ })).toBeEnabled();
  });

  test('на последней доступной странице «Вперёд» отключена', () => {
    setup({ page: 5, totalPages: 5 });
    expect(screen.getByRole('button', { name: /Вперёд/ })).toBeDisabled();
  });

  test('переход по страницам', () => {
    const { onPageChange } = setup({ page: 3, totalPages: 5 });
    fireEvent.click(screen.getByRole('button', { name: /Вперёд/ }));
    expect(onPageChange).toHaveBeenCalledWith(4);
    fireEvent.click(screen.getByRole('button', { name: /Назад/ }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });
});

describe('ограничение окна выборки', () => {
  test('при total=250000 и size=20 последняя страница 5000, а не 12500', () => {
    // Без поправки ceil(250000/20) предложил бы страницу 5001 → backend 422.
    const { totalPages, windowLimited } = computePagination(250000, 20, 100000);
    expect(totalPages).toBe(5000);
    expect(windowLimited).toBe(true);

    setup({ page: totalPages, totalPages, windowLimited, maxResultWindow: 100000 });

    expect(screen.getByText('Стр. 5000 из 5000')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Вперёд/ })).toBeDisabled();
  });

  test('при ограничении показано пояснение с числом доступных записей', () => {
    setup({ page: 1, totalPages: 5000, windowLimited: true, maxResultWindow: 100000 });
    expect(screen.getByText(/Доступны первые/)).toBeInTheDocument();
    expect(screen.getByText(/сузьте период или фильтры/)).toBeInTheDocument();
  });

  test('без ограничения пояснения нет', () => {
    setup({ page: 1, totalPages: 5, windowLimited: false });
    expect(screen.queryByText(/Доступны первые/)).toBeNull();
  });
});
