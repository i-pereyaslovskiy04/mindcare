import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MaterialsPage from './MaterialsPage';
import { getArticles, getArticleTags, getPublicCategories } from '../../../api/articles.api';
import {
  addFavorite, getFavoriteIds, getFavoriteMaterials, removeFavorite,
} from '../../../api/materialFavorites.api';
import { useAuth } from '../../../features/auth/AuthContext';

jest.mock('../../../api/articles.api');
jest.mock('../../../api/materialFavorites.api');
jest.mock('../../../features/auth/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });

const ARTICLE = {
  uuid: 'uuid-1',
  title: 'Сон и учёба',
  excerpt: 'Как высыпаться в сессию',
  published_at: '2026-10-01T09:00:00Z',
  cover_image_url: '/media/cover.jpg',
  categories: [{ id: 3, name: 'Статья' }],
  tags: [{ uuid: 't1', name: 'Сон' }],
};
const SECOND = { ...ARTICLE, uuid: 'uuid-2', title: 'Стресс перед экзаменом', tags: [] };

beforeAll(() => {
  window.matchMedia = window.matchMedia || ((query) => ({
    matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {},
  }));
});

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ isImpersonating: false });
  getPublicCategories.mockResolvedValue([{ id: 3, name: 'Статья' }]);
  getArticleTags.mockResolvedValue([{ uuid: 't1', name: 'Сон' }]);
  getFavoriteIds.mockResolvedValue({ uuids: ['uuid-2'], count: 1 });
});

describe('Student MaterialsPage', () => {
  it('компактные карточки ведут на чтение внутри кабинета; реальные тип, тема и дата', async () => {
    getArticles.mockResolvedValue({ items: [ARTICLE], total: 1 });
    render(<MaterialsPage />);

    const link = await screen.findByRole('link', { name: 'Сон и учёба' });
    expect(link).toHaveAttribute('href', '/student/materials/uuid-1');
    expect(screen.getByText('Статья')).toBeInTheDocument();
    expect(screen.getByText('Сон')).toBeInTheDocument();
    expect(screen.getByText('1 октября 2026 г.')).toBeInTheDocument();
    expect(screen.queryByText(/мин/)).toBeNull();
    expect(getArticles).toHaveBeenCalledWith(expect.objectContaining({ size: 8 }));
  });

  it('сердечко: состояние с сервера, добавление сохраняется только после ответа', async () => {
    getArticles.mockResolvedValue({ items: [ARTICLE, SECOND], total: 2 });
    addFavorite.mockResolvedValue(null);
    render(<MaterialsPage />);

    const off = await screen.findByRole('button', { name: 'Добавить «Сон и учёба» в избранное' });
    const on = await screen.findByRole('button', { name: 'Убрать «Стресс перед экзаменом» из избранного' });
    expect(off).toHaveAttribute('aria-pressed', 'false');
    expect(on).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /Избранное · 1/ })).toBeInTheDocument();

    userEvent.click(off);
    expect(addFavorite).toHaveBeenCalledWith('uuid-1');
    expect(await screen.findByRole('button', { name: 'Убрать «Сон и учёба» из избранного' }))
      .toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /Избранное · 2/ })).toBeInTheDocument();
  });

  it('ошибка сохранения избранного — отметка не меняется, сообщение показано', async () => {
    getArticles.mockResolvedValue({ items: [SECOND], total: 1 });
    removeFavorite.mockRejectedValue(new Error('Failed to fetch'));
    render(<MaterialsPage />);
    userEvent.click(await screen.findByRole('button', { name: 'Убрать «Стресс перед экзаменом» из избранного' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось сохранить избранное');
    expect(screen.getByRole('button', { name: 'Убрать «Стресс перед экзаменом» из избранного' }))
      .toHaveAttribute('aria-pressed', 'true');
  });

  it('фильтр «Избранное» берёт данные с сервера', async () => {
    getArticles.mockResolvedValue({ items: [ARTICLE, SECOND], total: 2 });
    getFavoriteMaterials.mockResolvedValue({ items: [SECOND], total: 1 });
    render(<MaterialsPage />);
    userEvent.click(await screen.findByRole('button', { name: /Избранное · 1/ }));
    await waitFor(() => expect(getFavoriteMaterials).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, size: 8 }),
    ));
    expect(await screen.findByRole('link', { name: 'Стресс перед экзаменом' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Сон и учёба' })).toBeNull();
  });

  it('в режиме «под именем» избранного нет и оно не запрашивается', async () => {
    useAuth.mockReturnValue({ isImpersonating: true });
    getArticles.mockResolvedValue({ items: [ARTICLE], total: 1 });
    render(<MaterialsPage />);
    await screen.findByRole('link', { name: 'Сон и учёба' });
    expect(getFavoriteIds).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /избранное/i })).toBeNull();
  });

  it('пустая выдача', async () => {
    getArticles.mockResolvedValue({ items: [], total: 0 });
    render(<MaterialsPage />);
    expect(await screen.findAllByText('Опубликованных материалов пока нет.')).not.toHaveLength(0);
  });

  it('сетевой сбой → сообщение и повтор', async () => {
    getArticles
      .mockRejectedValueOnce(new Error('Failed to fetch'))
      .mockResolvedValueOnce({ items: [ARTICLE], total: 1 });
    render(<MaterialsPage />);

    const alert = await screen.findByText(/Не удалось загрузить материалы/);
    expect(alert).toBeInTheDocument();
    userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(await screen.findByRole('link', { name: 'Сон и учёба' })).toBeInTheDocument();
  });

  it('фильтры: только тип материала, без сортировки и тем', async () => {
    getArticles.mockResolvedValue({ items: [ARTICLE], total: 1 });
    render(<MaterialsPage />);
    await screen.findByRole('link', { name: 'Сон и учёба' });

    userEvent.click(await screen.findByRole('button', { name: 'Фильтры' }));
    expect(screen.getByText('Тип материала')).toBeInTheDocument();
    expect(screen.queryByText('Сортировка')).toBeNull();
    expect(screen.queryByRole('radio')).toBeNull();

    userEvent.click(screen.getByRole('button', { name: 'Статья' }));
    await waitFor(() => expect(getArticles).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, category_id: 3 }),
    ));
  });
});
