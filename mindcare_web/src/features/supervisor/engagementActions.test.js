import { getEngagementActions } from './engagementActions';

const FREE = { id: 1, uuid: 's1', full_name: 'Ли Ан', current_engagement: null };
const LINKED = {
  id: 2, uuid: 's2', full_name: 'Петров Пётр',
  current_engagement: { id: 10, status: 'active', psychologist: { id: 7, full_name: 'Смирнова Ольга' } },
};

const ids = (student) => {
  const { primary, menu } = getEngagementActions(student, {});
  return { primary: primary.id, menu: menu.map((a) => a.id) };
};

test('без связи: основное «Назначить»; в меню результаты и контакты, закрытия нет', () => {
  expect(ids(FREE)).toEqual({ primary: 'assign', menu: ['results', 'contacts'] });
  expect(getEngagementActions(FREE, {}).primary.variant).toBe('primary');
});

test('со связью: основное «Переназначить»; в меню результаты, контакты, «Закрыть связь» (danger)', () => {
  expect(ids(LINKED)).toEqual({ primary: 'transfer', menu: ['results', 'contacts', 'close'] });
  expect(getEngagementActions(LINKED, {}).menu.find((a) => a.id === 'close').tone).toBe('danger');
});

test('действия вызывают обработчики страницы с самим студентом', () => {
  const h = {
    onAssign: jest.fn(), onTransfer: jest.fn(), onClose: jest.fn(),
    onResults: jest.fn(), onContacts: jest.fn(),
  };
  getEngagementActions(FREE, h).primary.onSelect();
  expect(h.onAssign).toHaveBeenCalledWith(FREE);

  const linked = getEngagementActions(LINKED, h);
  linked.primary.onSelect();
  linked.menu.forEach((a) => a.onSelect());
  expect(h.onTransfer).toHaveBeenCalledWith(LINKED);
  expect(h.onResults).toHaveBeenCalledWith(LINKED);
  expect(h.onContacts).toHaveBeenCalledWith(LINKED);
  expect(h.onClose).toHaveBeenCalledWith(LINKED);
});

test('доступные имена основного действия включают ФИО студента', () => {
  expect(getEngagementActions(FREE, {}).primary.ariaLabel).toBe('Назначить: Ли Ан');
  expect(getEngagementActions(LINKED, {}).primary.ariaLabel).toBe('Переназначить: Петров Пётр');
});
