import { render, screen } from '@testing-library/react';
import MaterialArticle from './MaterialArticle';

const ITEM = {
  uuid: 'a-1',
  title: 'Как справляться со стрессом',
  excerpt: 'Короткий лид',
  content: '<p>Безопасный текст</p><script>window.__pwned = true</script><img src="x" onerror="window.__pwned = true">',
  published_at: '2026-10-01T09:00:00Z',
  created_at: '2026-09-30T09:00:00Z',
  created_by_name: 'Редакция',
  cover_image_url: null,
  categories: [{ id: 1, name: 'Гид' }],
  tags: [{ uuid: 't1', name: 'Стресс' }, { uuid: 't2', name: 'Сон' }],
};

describe('MaterialArticle', () => {
  it('HTML проходит sanitization: script и обработчики событий вырезаются', () => {
    const { container } = render(<MaterialArticle item={ITEM} />);
    expect(screen.getByText('Безопасный текст')).toBeInTheDocument();
    // Проверка именно разметки после sanitization — запросов Testing Library для
    // <script> и атрибутов-обработчиков нет.
    // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access
    expect(container.querySelector('script')).toBeNull();
    // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access
    expect(container.querySelector('[onerror]')).toBeNull();
    expect(window.__pwned).toBeUndefined();
  });

  it('показывает реальные категорию, темы, дату и автора; времени чтения нет', () => {
    render(<MaterialArticle item={ITEM} />);
    expect(screen.getByRole('heading', { level: 1, name: ITEM.title })).toBeInTheDocument();
    expect(screen.getByText('Гид')).toBeInTheDocument();
    const topics = screen.getByRole('list', { name: 'Темы' });
    expect(topics).toHaveTextContent('Стресс');
    expect(topics).toHaveTextContent('Сон');
    expect(screen.getByText('1 октября 2026 г.')).toHaveAttribute('datetime', ITEM.published_at);
    expect(screen.getByText('Редакция')).toBeInTheDocument();
    expect(screen.queryByText(/мин/)).toBeNull();
  });

  it('без содержимого и лида — честная подпись', () => {
    render(<MaterialArticle item={{ ...ITEM, excerpt: '', content: '' }} />);
    expect(screen.getByText('Содержимое материала не добавлено.')).toBeInTheDocument();
  });
});
