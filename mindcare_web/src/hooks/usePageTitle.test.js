import { renderHook } from '@testing-library/react';
import { SITE_DEFAULT_TITLE, pageTitle, usePageTitle } from './usePageTitle';

test('pageTitle: раздел — Психология ДонГУ; без раздела — общий заголовок', () => {
  expect(pageTitle('О нас')).toBe('О нас — Психология ДонГУ');
  expect(pageTitle(null)).toBe(SITE_DEFAULT_TITLE);
});

test('usePageTitle ставит заголовок, следует за разделом и восстанавливает прежний', () => {
  document.title = 'прежний';
  const { rerender, unmount } = renderHook(({ s }) => usePageTitle(s), { initialProps: { s: 'Услуги' } });
  expect(document.title).toBe('Услуги — Психология ДонГУ');
  rerender({ s: 'Материалы' });
  expect(document.title).toBe('Материалы — Психология ДонГУ');
  unmount();
  expect(document.title).toBe('прежний');
});
