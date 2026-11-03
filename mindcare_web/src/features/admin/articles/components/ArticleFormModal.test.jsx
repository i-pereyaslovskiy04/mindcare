import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ArticleFormModal from './ArticleFormModal';
import {
  createArticle, createMyArticle, getAdminCategories, getPublicCategories, updateMyArticle,
} from '../../../../api/articles.api';
import { getTagsPublic } from '../../../../api/tags.api';

jest.mock('../../../../api/articles.api');
jest.mock('../../../../api/tags.api');
// Tiptap (ESM) и загрузка изображения в jsdom не нужны: простые заглушки.
jest.mock('../../../../components/UI/TiptapEditor/TiptapEditor', () => ({ value, onChange }) => (
  <textarea aria-label="Содержимое" value={value} onChange={e => onChange(e.target.value)} />
));
jest.mock('../../../../components/UI/ImageUpload/ImageUpload', () => () => null);

beforeEach(() => {
  jest.clearAllMocks();
  getTagsPublic.mockResolvedValue([]);
  getPublicCategories.mockResolvedValue([{ id: 3, name: 'Статья' }]);
  getAdminCategories.mockResolvedValue([{ id: 3, name: 'Статья' }]);
});

describe('ArticleFormModal — режим автора (психолог)', () => {
  it('без полей публикации; публичные категории; сохраняет черновик своим API', async () => {
    createMyArticle.mockResolvedValue({ uuid: 'a-1', status: 'draft' });
    const onSaved = jest.fn();
    render(<ArticleFormModal open mode="author" article={null} onClose={jest.fn()} onSaved={onSaved} />);

    await waitFor(() => expect(getPublicCategories).toHaveBeenCalled());
    expect(getAdminCategories).not.toHaveBeenCalled();
    expect(screen.queryByText('Дата публикации')).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(screen.getByText(/сохранится черновиком/)).toBeInTheDocument();

    userEvent.type(screen.getByPlaceholderText('Введите заголовок'), 'Мой материал');
    userEvent.click(screen.getByRole('button', { name: 'Сохранить черновик' }));
    await waitFor(() => expect(createMyArticle).toHaveBeenCalledTimes(1));
    const payload = createMyArticle.mock.calls[0][0];
    expect(payload.title).toBe('Мой материал');
    expect(payload).not.toHaveProperty('is_published');
    expect(payload).not.toHaveProperty('published_at');
    expect(createArticle).not.toHaveBeenCalled();
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it('правка опубликованной — предупреждение в форме', async () => {
    updateMyArticle.mockResolvedValue({ uuid: 'a-1', status: 'draft' });
    const article = {
      uuid: 'a-1', title: 'Опубликованная', status: 'published', is_published: true,
      categories: [], tags: [], content: '<p>x</p>', excerpt: '',
    };
    render(<ArticleFormModal open mode="author" article={article} onClose={jest.fn()} onSaved={jest.fn()} />);
    expect(screen.getByText(/снимет его с публикации/)).toBeInTheDocument();
    userEvent.click(screen.getByRole('button', { name: 'Сохранить черновик' }));
    await waitFor(() => expect(updateMyArticle).toHaveBeenCalledWith('a-1', expect.not.objectContaining({
      is_published: expect.anything(),
    }), 'psychologist'));
  });
});

describe('ArticleFormModal — режим автора (супервизор)', () => {
  it('подсказка о самостоятельной публикации; API супервизора', async () => {
    createMyArticle.mockResolvedValue({ uuid: 'a-2', status: 'draft' });
    render(<ArticleFormModal open mode="author" authorRole="supervisor" article={null}
      onClose={jest.fn()} onSaved={jest.fn()} />);
    await waitFor(() => expect(getPublicCategories).toHaveBeenCalled());
    expect(screen.getByText(/кнопкой «Опубликовать» в списке/)).toBeInTheDocument();
    expect(screen.queryByText(/на проверку супервизору/)).toBeNull();
    userEvent.type(screen.getByPlaceholderText('Введите заголовок'), 'Материал супервизора');
    userEvent.click(screen.getByRole('button', { name: 'Сохранить черновик' }));
    await waitFor(() => expect(createMyArticle).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Материал супервизора' }), 'supervisor',
    ));
  });
});

describe('ArticleFormModal — режим админа не изменился', () => {
  it('поля публикации и админский API', async () => {
    render(<ArticleFormModal open article={null} onClose={jest.fn()} onSaved={jest.fn()} />);
    await waitFor(() => expect(getAdminCategories).toHaveBeenCalled());
    expect(screen.getByText('Дата публикации')).toBeInTheDocument();
    expect(screen.getByRole('checkbox')).toBeInTheDocument();
  });
});
