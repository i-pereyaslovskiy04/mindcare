/**
 * Хлебные крошки шапки кабинета — только из явных подписей layout'а.
 *
 * Подписи НЕ строятся из сегментов URL: layout передаёт карту
 * `crumbLabels` (путь → подпись) и, для страниц с параметром в пути,
 * `dynamicCrumbs` ({ prefix, label, parent? }, parent — путь раздела из
 * crumbLabels, который становится промежуточной крошкой-ссылкой).
 *
 * Результат — массив { label, to? }: первая крошка всегда «Главная» (ссылка
 * на корень кабинета), у последней нет `to` — это текущая страница. На самом
 * корне кабинета «Главная» и есть текущая страница.
 */

export const HOME_CRUMB_LABEL = 'Главная';

const trimSlash = (path) => (path.length > 1 && path.endsWith('/') ? path.slice(0, -1) : path);

export function resolveBreadcrumbs({ pathname, homePath, crumbLabels = {}, dynamicCrumbs = [] }) {
  const path = trimSlash(pathname);
  if (path === homePath) return [{ label: HOME_CRUMB_LABEL }];

  const home = { label: HOME_CRUMB_LABEL, to: homePath };

  if (crumbLabels[path]) return [home, { label: crumbLabels[path] }];

  const dynamic = dynamicCrumbs.find(({ prefix }) => path.startsWith(prefix));
  if (dynamic) {
    const parentLabel = dynamic.parent ? crumbLabels[dynamic.parent] : null;
    return parentLabel
      ? [home, { label: parentLabel, to: dynamic.parent }, { label: dynamic.label }]
      : [home, { label: dynamic.label }];
  }

  // Вложенная страница без собственной подписи (например,
  // /student/tests/catalog): показываем ближайший известный раздел ссылкой,
  // а не придумываем название из URL.
  const section = Object.keys(crumbLabels)
    .filter((p) => p !== homePath && path.startsWith(`${p}/`))
    .sort((a, b) => b.length - a.length)[0];
  if (section) return [home, { label: crumbLabels[section], to: section }];

  return [home];
}
