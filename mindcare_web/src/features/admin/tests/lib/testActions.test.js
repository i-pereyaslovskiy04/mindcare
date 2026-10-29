import { getTestActions } from './testActions';

const handlers = () => ({
  onPreview: jest.fn(), onEdit: jest.fn(), onDelete: jest.fn(), onPublish: jest.fn(),
  onReturn: jest.fn(), onSubmitForReview: jest.fn(), onToggleActive: jest.fn(),
});
// Обработчики так, как их передают страницы (AdminTestsPage / PsychologistTestsPage).
const moderatorHandlers = () => {
  const { onSubmitForReview, ...rest } = handlers();
  return rest;
};
const authorHandlers = () => {
  const { onPreview, onEdit, onDelete, onSubmitForReview } = handlers();
  return { onPreview, onEdit, onDelete, onSubmitForReview };
};

const test_ = (status, extra = {}) => ({ uuid: `u-${status}`, title: 'Тест', status, is_active: true, ...extra });
const summary = ({ primary, menu }) => ({
  primary: primary && primary.label,
  menu: menu.map((a) => a.label),
});

describe('moderator — /admin/tests и /supervisor/tests', () => {
  const run = (status, extra) => summary(getTestActions(test_(status, extra), {
    context: 'moderator', ...moderatorHandlers(),
  }));

  test('in_review: основное «Опубликовать», в меню «Вернуть на доработку» и остальное', () => {
    expect(run('in_review')).toEqual({
      primary: 'Опубликовать',
      menu: ['Вернуть на доработку', 'Предпросмотр', 'Скрыть из каталога', 'Редактировать', 'Удалить'],
    });
  });

  test('draft и needs_changes: основное «Редактировать», «Опубликовать» в меню, без возврата', () => {
    ['draft', 'needs_changes'].forEach((status) => {
      expect(run(status)).toEqual({
        primary: 'Редактировать',
        menu: ['Опубликовать', 'Предпросмотр', 'Скрыть из каталога', 'Удалить'],
      });
    });
  });

  test('published: без «Опубликовать» и возврата', () => {
    expect(run('published')).toEqual({
      primary: 'Редактировать', menu: ['Предпросмотр', 'Скрыть из каталога', 'Удалить'],
    });
  });

  test('видимость: скрытый — «Показать в каталоге», активный — «Скрыть из каталога» (danger)', () => {
    expect(run('published', { is_active: false }).menu).toContain('Показать в каталоге');
    const { menu } = getTestActions(test_('published'), { context: 'moderator', ...moderatorHandlers() });
    expect(menu.find((a) => a.id === 'toggle').tone).toBe('danger');
  });

  test('«Отправить на модерацию» модератору не показывается', () => {
    ['draft', 'needs_changes', 'in_review', 'published'].forEach((status) => {
      expect(summary(getTestActions(test_(status), { context: 'moderator', ...handlers() })).menu)
        .not.toContain('Отправить на модерацию');
    });
  });
});

describe('author — /psychologist/tests (свои тесты)', () => {
  const run = (status) => summary(getTestActions(test_(status), { context: 'author', ...authorHandlers() }));

  test('draft и needs_changes: «Редактировать», в меню отправка, предпросмотр, удаление', () => {
    ['draft', 'needs_changes'].forEach((status) => {
      expect(run(status)).toEqual({
        primary: 'Редактировать',
        menu: ['Отправить на модерацию', 'Предпросмотр', 'Удалить'],
      });
    });
  });

  test('in_review: только «Предпросмотр» — ни правки, ни удаления (ADR-016)', () => {
    expect(run('in_review')).toEqual({ primary: 'Предпросмотр', menu: [] });
  });

  test('published: основное «Предпросмотр», «Редактировать» в меню, удалить нельзя', () => {
    expect(run('published')).toEqual({ primary: 'Предпросмотр', menu: ['Редактировать'] });
  });

  test('модерация и видимость автору недоступны даже при переданных обработчиках', () => {
    ['draft', 'needs_changes', 'in_review', 'published'].forEach((status) => {
      const { primary, menu } = summary(getTestActions(test_(status), { context: 'author', ...handlers() }));
      [primary, ...menu].forEach((label) => {
        expect(['Опубликовать', 'Вернуть на доработку', 'Скрыть из каталога', 'Показать в каталоге'])
          .not.toContain(label);
      });
    });
  });
});

test('действие вызывает обработчик с тестом; основное — variant по смыслу', () => {
  const h = moderatorHandlers();
  const item = test_('in_review');
  const { primary, menu } = getTestActions(item, { context: 'moderator', ...h });
  expect(primary.variant).toBe('primary');
  primary.onSelect();
  expect(h.onPublish).toHaveBeenCalledWith(item);
  menu.find((a) => a.id === 'return').onSelect();
  expect(h.onReturn).toHaveBeenCalledWith(item);
  const del = menu.find((a) => a.id === 'delete');
  expect(del.tone).toBe('danger');
  del.onSelect();
  expect(h.onDelete).toHaveBeenCalledWith(item);
  expect(getTestActions(test_('draft'), { context: 'moderator', ...h }).primary.variant).toBe('secondary');
});

test('pending: выполняющееся действие недоступно только у своей строки', () => {
  const pending = { publish: 'u-in_review', toggle: 'u-in_review', preview: 'other' };
  const mine = getTestActions(test_('in_review'), { context: 'moderator', pending, ...moderatorHandlers() });
  expect(mine.primary.disabled).toBe(true);
  expect(mine.menu.find((a) => a.id === 'toggle').disabled).toBe(true);
  expect(mine.menu.find((a) => a.id === 'preview').disabled).toBe(false);
  expect(mine.menu.find((a) => a.id === 'edit').disabled).toBe(false);

  const other = getTestActions(test_('draft'), { context: 'moderator', pending, ...moderatorHandlers() });
  expect(other.menu.find((a) => a.id === 'publish').disabled).toBe(false);

  const author = getTestActions(test_('draft'), {
    context: 'author', pending: { submit: 'u-draft' }, ...authorHandlers(),
  });
  expect(author.menu.find((a) => a.id === 'submit').disabled).toBe(true);
});

test('без обработчика действие не показывается', () => {
  const { onToggleActive, ...rest } = moderatorHandlers();
  expect(summary(getTestActions(test_('published'), { context: 'moderator', ...rest })).menu)
    .toEqual(['Предпросмотр', 'Удалить']);
});
