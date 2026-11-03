import { useEffect } from 'react';

export const SITE_TITLE = 'Психология ДонГУ';
export const SITE_DEFAULT_TITLE = `${SITE_TITLE} — Центр психологической помощи`;

/** «<Раздел> — Психология ДонГУ»; без раздела — общий заголовок сайта. */
export function pageTitle(section) {
  return section ? `${section} — ${SITE_TITLE}` : SITE_DEFAULT_TITLE;
}

/**
 * Заголовок вкладки браузера для страницы. При размонтировании возвращает
 * прежний, чтобы страница без своего заголовка не унаследовала чужой.
 */
export function usePageTitle(section) {
  useEffect(() => {
    const previous = document.title;
    document.title = pageTitle(section);
    return () => { document.title = previous; };
  }, [section]);
}
