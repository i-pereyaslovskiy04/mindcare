import { render, screen } from '@testing-library/react';
import MaterialView from './MaterialView';
import { useMaterial } from '../hooks/useMaterial';

jest.mock('../hooks/useMaterial');
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });

const refetch = jest.fn();

beforeEach(() => jest.clearAllMocks());

describe('MaterialView', () => {
  it('возврат ведёт в библиотеку текущего кабинета', () => {
    useMaterial.mockReturnValue({ status: 'loading', item: null, refetch });
    render(<MaterialView uuid="a-1" backTo="/psychologist/materials" />);
    expect(screen.getByRole('link', { name: '← Все материалы' }))
      .toHaveAttribute('href', '/psychologist/materials');
    expect(screen.getByRole('status')).toHaveTextContent('Загружаем материал');
  });

  it('недоступный материал: без содержимого', () => {
    useMaterial.mockReturnValue({ status: 'notFound', item: null, refetch });
    render(<MaterialView uuid="a-1" backTo="/student/materials" />);
    expect(screen.getByText('Материал недоступен')).toBeInTheDocument();
    expect(screen.queryByRole('article')).toBeNull();
  });

  it('ошибка загрузки → повтор', () => {
    useMaterial.mockReturnValue({ status: 'error', item: null, refetch });
    render(<MaterialView uuid="a-1" backTo="/student/materials" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Не удалось загрузить материал');
    screen.getByRole('button', { name: 'Повторить' }).click();
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});
