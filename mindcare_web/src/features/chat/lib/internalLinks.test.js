import { INTERNAL_LINKS, replaceInternalLinks } from './internalLinks';
import { INTERNAL_LINKS as LINKIFIED_INTERNAL_LINKS } from './LinkifiedText';

// LinkifiedText импортирует react-router-dom (v7 не резолвится jest-резолвером).
jest.mock('react-router-dom', () => ({ Link: () => null }), { virtual: true });

describe('internalLinks', () => {
  test('LinkifiedText использует тот же allowlist', () => {
    expect(LINKIFIED_INTERNAL_LINKS).toBe(INTERNAL_LINKS);
  });

  test('путь из allowlist заменяется подписью, пунктуация и текст сохраняются', () => {
    expect(replaceInternalLinks('Откройте /student/settings#student-verification.'))
      .toBe('Откройте Подтверждение студента ДонГУ.');
    expect(replaceInternalLinks('(/student/settings#student-verification)'))
      .toBe('(Подтверждение студента ДонГУ)');
  });

  test('прочие и «склеенные» пути остаются текстом', () => {
    const text = 'x/student/settings#student-verification /student/settings#student-verification-x //host/a';
    expect(replaceInternalLinks(text)).toBe(text);
  });

  test('пустой текст', () => {
    expect(replaceInternalLinks('')).toBe('');
    expect(replaceInternalLinks(null)).toBe('');
  });
});
