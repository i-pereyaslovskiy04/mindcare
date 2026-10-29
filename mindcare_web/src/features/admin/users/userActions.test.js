import { canDeactivate, canImpersonate, getUserActions, isDisabled } from './userActions';

const ME = 1;
const base = { email: 'x@donnu.ru', deleted_at: null, is_active: true, roles: ['psychologist', 'student'] };
const USERS = {
  self: { ...base, id: ME, uuid: 'me', full_name: 'Я Админ', roles: ['admin', 'student'] },
  active: { ...base, id: 2, uuid: 'active', full_name: 'Активный Психолог' },
  otherAdmin: { ...base, id: 3, uuid: 'admin2', full_name: 'Другой Админ', roles: ['admin'] },
  disabled: { ...base, id: 4, uuid: 'off', full_name: 'Отключён', is_active: false },
  deleted: { ...base, id: 5, uuid: 'deleted', full_name: 'Удалён Ранее', is_active: false, deleted_at: '2025-01-01T00:00:00Z' },
};

const ids = (item, ctx = {}) => {
  const { primary, menu } = getUserActions(item, { currentUserId: ME, ...ctx });
  return { primary: primary?.id ?? null, menu: menu.map((a) => a.id) };
};

test('матрица действий: основное + меню (правила прежние)', () => {
  expect(ids(USERS.self)).toEqual({ primary: 'edit', menu: [] });
  expect(ids(USERS.active)).toEqual({ primary: 'edit', menu: ['impersonate', 'deactivate'] });
  expect(ids(USERS.otherAdmin)).toEqual({ primary: 'edit', menu: ['deactivate'] });
  expect(ids(USERS.disabled)).toEqual({ primary: 'edit', menu: ['restore'] });
  expect(ids(USERS.deleted)).toEqual({ primary: 'restore', menu: [] });
});

test('guard-функции: себя нельзя отключить и «зайти под собой»; админа — только отключить', () => {
  expect(canDeactivate(USERS.self, ME)).toBe(false);
  expect(canImpersonate(USERS.self, ME)).toBe(false);
  expect(canImpersonate(USERS.otherAdmin, ME)).toBe(false);
  expect(canDeactivate(USERS.otherAdmin, ME)).toBe(true);
  expect(canImpersonate(USERS.disabled, ME)).toBe(false);
  expect(isDisabled(USERS.deleted)).toBe(true);
  expect(isDisabled({ ...USERS.active, is_active: null })).toBe(false); // исторический NULL — активен
});

test('действия вызывают обработчики страницы с самим пользователем', () => {
  const handlers = { onEdit: jest.fn(), onDeactivate: jest.fn(), onRestore: jest.fn(), onImpersonate: jest.fn() };
  const { primary, menu } = getUserActions(USERS.active, { currentUserId: ME, ...handlers });
  primary.onSelect();
  menu.forEach((a) => a.onSelect());
  expect(handlers.onEdit).toHaveBeenCalledWith(USERS.active);
  expect(handlers.onImpersonate).toHaveBeenCalledWith(USERS.active);
  expect(handlers.onDeactivate).toHaveBeenCalledWith(USERS.active);

  getUserActions(USERS.deleted, { currentUserId: ME, ...handlers }).primary.onSelect();
  expect(handlers.onRestore).toHaveBeenCalledWith(USERS.deleted);
});

test('пока идёт вход под именем, «Зайти под именем» недоступно', () => {
  const { menu } = getUserActions(USERS.active, { currentUserId: ME, pendingImpersonation: true });
  expect(menu.find((a) => a.id === 'impersonate').disabled).toBe(true);
});

test('доступные имена основного действия включают ФИО', () => {
  expect(getUserActions(USERS.active, { currentUserId: ME }).primary.ariaLabel)
    .toBe('Редактировать Активный Психолог');
  expect(getUserActions(USERS.deleted, { currentUserId: ME }).primary.ariaLabel)
    .toBe('Восстановить Удалён Ранее');
});
