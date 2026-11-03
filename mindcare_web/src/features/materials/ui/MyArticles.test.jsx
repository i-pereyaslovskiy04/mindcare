import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MyArticles from './MyArticles';
import {
  deleteMyArticle, getMyArticle, getMyArticles, publishMyArticle, submitMyArticle,
} from '../../../api/articles.api';

jest.mock('../../../api/articles.api');
// Форма статьи тянет Tiptap (ESM) — в этом тесте проверяется только открытие.
jest.mock('../../admin/articles/components/ArticleFormModal', () => (props) => (
  <div role="dialog" aria-label="Форма материала">{props.mode}:{props.article?.uuid || 'new'}</div>
));

const item = (n, extra = {}) => ({
  uuid: `a-${n}`, title: `Статья ${n}`, excerpt: '', status: 'draft', is_published: false,
  created_at: '2026-10-20T09:00:00Z', published_at: null, review_comment: null, ...extra,
});
const page = (items) => ({ items, total: items.length, page: 1, size: 10 });
const apiError = (status, body = {}) => Object.assign(new Error('x'), { status, body });

beforeEach(() => jest.clearAllMocks());

describe('MyArticles', () => {
  it('статусы модерации, комментарий проверяющего и доступные действия', async () => {
    getMyArticles.mockResolvedValue(page([
      item(1),
      item(2, { status: 'needs_changes', review_comment: 'Уточните источники' }),
      item(3, { status: 'in_review' }),
      item(4, { status: 'published', is_published: true, published_at: '2026-10-21T09:00:00Z' }),
    ]));
    render(<MyArticles />);
    const rows = await screen.findAllByRole('listitem');
    expect(within(rows[0]).getByText('Черновик')).toBeInTheDocument();
    expect(within(rows[1]).getByText('На доработке')).toBeInTheDocument();
    expect(within(rows[1]).getByText(/Уточните источники/)).toBeInTheDocument();
    expect(within(rows[2]).getByText('На проверке')).toBeInTheDocument();
    expect(within(rows[2]).queryByRole('button', { name: 'Редактировать' })).toBeNull();
    expect(within(rows[3]).getByText('Опубликовано')).toBeInTheDocument();
    expect(within(rows[3]).queryByRole('button', { name: 'Удалить' })).toBeNull();
    expect(within(rows[3]).queryByRole('button', { name: 'Отправить на проверку' })).toBeNull();
  });

  it('отправка на проверку — запрос и перечитывание списка', async () => {
    getMyArticles.mockResolvedValueOnce(page([item(1)]))
      .mockResolvedValueOnce(page([item(1, { status: 'in_review' })]));
    submitMyArticle.mockResolvedValue(item(1, { status: 'in_review' }));
    render(<MyArticles />);
    userEvent.click(await screen.findByRole('button', { name: 'Отправить на проверку' }));
    expect(submitMyArticle).toHaveBeenCalledWith('a-1');
    expect(await screen.findByText('На проверке')).toBeInTheDocument();
  });

  it('409 — понятное сообщение и обновлённый список', async () => {
    getMyArticles.mockResolvedValueOnce(page([item(1)]))
      .mockResolvedValueOnce(page([item(1, { status: 'in_review' })]));
    submitMyArticle.mockRejectedValue(apiError(409, { current_status: 'in_review' }));
    render(<MyArticles />);
    userEvent.click(await screen.findByRole('button', { name: 'Отправить на проверку' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('«На проверке»');
    await waitFor(() => expect(getMyArticles).toHaveBeenCalledTimes(2));
  });

  it('правка опубликованной — сначала предупреждение о снятии с публикации', async () => {
    getMyArticles.mockResolvedValue(page([item(4, { status: 'published', is_published: true })]));
    getMyArticle.mockResolvedValue({ ...item(4, { status: 'published' }), content: '<p>x</p>' });
    render(<MyArticles />);
    userEvent.click(await screen.findByRole('button', { name: 'Редактировать' }));
    const warn = screen.getByRole('dialog', { name: 'Редактировать опубликованный материал?' });
    expect(warn).toHaveTextContent('снимется с публикации');
    expect(getMyArticle).not.toHaveBeenCalled();
    userEvent.click(within(warn).getByRole('button', { name: 'Редактировать' }));
    expect(await screen.findByRole('dialog', { name: 'Форма материала' })).toHaveTextContent('author:a-4');
  });

  it('удаление черновика — с подтверждением', async () => {
    getMyArticles.mockResolvedValue(page([item(1)]));
    deleteMyArticle.mockResolvedValue(null);
    render(<MyArticles />);
    userEvent.click(await screen.findByRole('button', { name: 'Удалить' }));
    expect(deleteMyArticle).not.toHaveBeenCalled();
    const dialog = screen.getByRole('dialog', { name: 'Удалить материал?' });
    userEvent.click(within(dialog).getByRole('button', { name: 'Удалить' }));
    await waitFor(() => expect(deleteMyArticle).toHaveBeenCalledWith('a-1', 'psychologist'));
  });

  it('новый материал открывает форму автора', async () => {
    getMyArticles.mockResolvedValue(page([]));
    render(<MyArticles />);
    expect(await screen.findByText('Вы ещё не создали ни одного материала.')).toBeInTheDocument();
    userEvent.click(screen.getByRole('button', { name: 'Новый материал' }));
    expect(screen.getByRole('dialog', { name: 'Форма материала' })).toHaveTextContent('author:new');
  });

  it('фильтр по статусу уходит на сервер', async () => {
    getMyArticles.mockResolvedValue(page([]));
    render(<MyArticles />);
    await screen.findByText('Вы ещё не создали ни одного материала.');
    userEvent.click(screen.getByRole('button', { name: 'На доработке' }));
    await waitFor(() => expect(getMyArticles).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, status: 'needs_changes' }), 'psychologist',
    ));
  });
});

describe('MyArticles — супервизор публикует сам', () => {
  it('API супервизора, без «На проверке» и без отправки на проверку', async () => {
    getMyArticles.mockResolvedValue(page([item(1), item(2, { status: 'needs_changes' })]));
    render(<MyArticles role="supervisor" />);
    const rows = await screen.findAllByRole('listitem');
    expect(getMyArticles).toHaveBeenCalledWith(expect.objectContaining({ page: 1 }), 'supervisor');
    expect(screen.queryByRole('button', { name: 'На проверке' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Отправить на проверку' })).toBeNull();
    expect(within(rows[0]).getByRole('button', { name: 'Опубликовать' })).toBeInTheDocument();
    expect(within(rows[1]).getByRole('button', { name: 'Опубликовать' })).toBeInTheDocument();
  });

  it('публикация — после подтверждения, затем список перечитывается', async () => {
    getMyArticles.mockResolvedValueOnce(page([item(1)]))
      .mockResolvedValueOnce(page([item(1, { status: 'published', is_published: true })]));
    publishMyArticle.mockResolvedValue(item(1, { status: 'published' }));
    render(<MyArticles role="supervisor" />);
    userEvent.click(await screen.findByRole('button', { name: 'Опубликовать' }));
    expect(publishMyArticle).not.toHaveBeenCalled();
    const dialog = screen.getByRole('dialog', { name: 'Опубликовать материал?' });
    userEvent.click(within(dialog).getByRole('button', { name: 'Опубликовать' }));
    await waitFor(() => expect(publishMyArticle).toHaveBeenCalledWith('a-1'));
    expect(submitMyArticle).not.toHaveBeenCalled();
    expect(await screen.findByText('Опубликовано')).toBeInTheDocument();
  });

  it('правка опубликованной — предупреждение без «отправить на проверку»', async () => {
    getMyArticles.mockResolvedValue(page([item(4, { status: 'published', is_published: true })]));
    getMyArticle.mockResolvedValue({ ...item(4, { status: 'published' }), content: '<p>x</p>' });
    render(<MyArticles role="supervisor" />);
    userEvent.click(await screen.findByRole('button', { name: 'Редактировать' }));
    const warn = screen.getByRole('dialog', { name: 'Редактировать опубликованный материал?' });
    expect(warn).toHaveTextContent('опубликуйте его снова');
    userEvent.click(within(warn).getByRole('button', { name: 'Редактировать' }));
    await waitFor(() => expect(getMyArticle).toHaveBeenCalledWith('a-4', 'supervisor'));
  });
});
