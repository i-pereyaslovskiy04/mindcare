import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ArticleReview from './ArticleReview';
import {
  getReviewArticle, getReviewArticles, publishReviewArticle, returnReviewArticle,
} from '../../../api/articles.api';
import { subscribeReviewQueueChanged } from '../../moderation/lib/reviewQueueEvents';

jest.mock('../../../api/articles.api');

const ITEM = {
  uuid: 'a-1', title: 'Сон и учёба', excerpt: 'Коротко', status: 'in_review',
  created_at: '2026-10-20T09:00:00Z', created_by_name: 'Иванова Ирина',
};
const page = (items) => ({ items, total: items.length, page: 1, size: 20 });

beforeEach(() => jest.clearAllMocks());

describe('ArticleReview', () => {
  it('очередь на проверке с автором', async () => {
    getReviewArticles.mockResolvedValue(page([ITEM]));
    render(<ArticleReview />);
    const row = await screen.findByRole('listitem');
    expect(row).toHaveTextContent('Сон и учёба');
    expect(row).toHaveTextContent('Иванова Ирина');
  });

  it('публикация — после подтверждения, затем очередь обновляется', async () => {
    getReviewArticles.mockResolvedValueOnce(page([ITEM])).mockResolvedValueOnce(page([]));
    publishReviewArticle.mockResolvedValue({ ...ITEM, status: 'published' });
    render(<ArticleReview />);
    userEvent.click(await screen.findByRole('button', { name: 'Опубликовать' }));
    expect(publishReviewArticle).not.toHaveBeenCalled();
    const dialog = screen.getByRole('dialog', { name: 'Опубликовать материал?' });
    userEvent.click(within(dialog).getByRole('button', { name: 'Опубликовать' }));
    await waitFor(() => expect(publishReviewArticle).toHaveBeenCalledWith('a-1'));
    expect(await screen.findByText('Материалов на проверке нет.')).toBeInTheDocument();
  });

  it('возврат на доработку с комментарием', async () => {
    getReviewArticles.mockResolvedValue(page([ITEM]));
    returnReviewArticle.mockResolvedValue({ ...ITEM, status: 'needs_changes' });
    render(<ArticleReview />);
    userEvent.click(await screen.findByRole('button', { name: 'Вернуть на доработку' }));
    const dialog = screen.getByRole('dialog', { name: 'Вернуть на доработку' });
    userEvent.type(within(dialog).getByLabelText('Комментарий автору (необязательно)'), '  Добавьте источники ');
    userEvent.click(within(dialog).getByRole('button', { name: 'Вернуть' }));
    await waitFor(() => expect(returnReviewArticle).toHaveBeenCalledWith('a-1', 'Добавьте источники'));
  });

  it('409 — решение уже принято другим проверяющим', async () => {
    getReviewArticles.mockResolvedValue(page([ITEM]));
    publishReviewArticle.mockRejectedValue(Object.assign(new Error('x'), { status: 409 }));
    render(<ArticleReview />);
    userEvent.click(await screen.findByRole('button', { name: 'Опубликовать' }));
    userEvent.click(within(screen.getByRole('dialog', { name: 'Опубликовать материал?' }))
      .getByRole('button', { name: 'Опубликовать' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('другой проверяющий');
  });

  it('предпросмотр загружает полный текст', async () => {
    getReviewArticles.mockResolvedValue(page([ITEM]));
    getReviewArticle.mockResolvedValue({
      ...ITEM, content: '<p>Полный текст</p>', tags: [], categories: [], cover_image_url: null,
    });
    render(<ArticleReview />);
    userEvent.click(await screen.findByRole('button', { name: 'Просмотреть' }));
    expect(await screen.findByText('Полный текст')).toBeInTheDocument();
    expect(getReviewArticle).toHaveBeenCalledWith('a-1');
  });
});

describe('ArticleReview — бейдж меню', () => {
  it('решение сообщает об изменении очереди (бейдж обновляется сразу)', async () => {
    const listener = jest.fn();
    const unsubscribe = subscribeReviewQueueChanged(listener);
    getReviewArticles.mockResolvedValue(page([ITEM]));
    publishReviewArticle.mockResolvedValue({ ...ITEM, status: 'published' });
    render(<ArticleReview />);
    userEvent.click(await screen.findByRole('button', { name: 'Опубликовать' }));
    userEvent.click(within(screen.getByRole('dialog', { name: 'Опубликовать материал?' }))
      .getByRole('button', { name: 'Опубликовать' }));
    await waitFor(() => expect(listener).toHaveBeenCalledTimes(1));
    unsubscribe();
  });
});
