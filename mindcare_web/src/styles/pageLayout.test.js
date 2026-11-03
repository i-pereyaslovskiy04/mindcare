import fs from 'fs';
import path from 'path';

// Контракт раскладки страниц кабинетов (без пиксельных проверок — jsdom CSS
// не применяет): одна колонка контента в layout'ах, узкие страницы-формы
// центрируются на уровне корня, рабочие страницы не дублируют контейнер,
// навигационные вкладки — только shared Tabs.

const SRC = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(SRC, rel), 'utf8');
const block = (css, selector) => {
  const start = css.indexOf(`${selector} {`);
  expect(start).toBeGreaterThanOrEqual(0);
  return css.slice(start, css.indexOf('}', start));
};

test('ширины кабинета — токены в variables.css', () => {
  const vars = read('styles/variables.css');
  expect(vars).toMatch(/--cabinet-content-max:\s*1180px;/);
  expect(vars).toMatch(/--cabinet-narrow-max:\s*760px;/);
});

test.each([
  'components/CabinetLayout/CabinetLayout.module.css',
  'features/admin/AdminLayout.module.css',
])('%s: .contentInner — колонка по токену, по центру', (file) => {
  const inner = block(read(file), '.contentInner');
  expect(inner).toMatch(/width:\s*100%;/);
  expect(inner).toMatch(/max-width:\s*var\(--cabinet-content-max\);/);
  expect(inner).toMatch(/margin:\s*0 auto;/);
});

const NARROW_PAGES = [
  'pages/student/Settings/SettingsPage.module.css',
  'components/CabinetLayout/CabinetSettingsPage.module.css',
  'features/admin/settings/pages/AdminSettingsPage.module.css',
  'features/admin/email-domains/pages/EmailDomainsPage.module.css',
  'pages/supervisor/BookingPage.module.css',
];

test.each(NARROW_PAGES)('%s: страница-форма — узкий корень по центру', (file) => {
  const page = block(read(file), '.page');
  expect(page).toMatch(/width:\s*100%;/);
  expect(page).toMatch(/max-width:\s*var\(--cabinet-narrow-max\);/);
  expect(page).toMatch(/margin-inline:\s*auto;/);
});

test('у детей страниц-форм нет своей ширины колонки (иначе колонка снова уезжает влево)', () => {
  [
    ...NARROW_PAGES,
    'features/accountSettings/ui/AccountSettings.module.css',
  ].forEach((file) => {
    expect(read(file)).not.toMatch(/max-width:\s*(520|680|760)px/);
  });
});

test.each([
  'pages/psychologist/PsychologistStudentsPage.module.css',
  'pages/supervisor/EngagementsPage.module.css',
  'pages/supervisor/StudentVerificationsPage.module.css',
])('%s: рабочая страница не дублирует контейнер кабинета', (file) => {
  const css = read(file);
  expect(css).not.toMatch(/max-width:\s*1100px/);
  expect(css).not.toMatch(/\.page\s*\{[^}]*padding/);
});

test('фильтры /admin/users переносятся на узкой ширине', () => {
  const filters = block(read('features/admin/users/components/UsersFilters.module.css'), '.filters');
  expect(filters).toMatch(/flex-wrap:\s*wrap;/);
});

test('дневник: колонка формы сжимается, не выталкивая историю за контейнер', () => {
  expect(block(read('pages/student/DiaryPage.module.css'), '.layout'))
    .toMatch(/grid-template-columns:\s*minmax\(0, 1fr\) 380px;/);
});

// Переключатель «Вход / Регистрация» в AuthModal — выбор типа формы внутри
// модалки, не навигация по разделам страницы.
const OWN_TABLIST_ALLOWED = ['features/auth/ui/AuthModal.jsx'];

test('role="tablist" — только в shared Tabs (локальных вкладок нет)', () => {
  const found = [];
  const walk = (dir) => {
    fs.readdirSync(dir, { withFileTypes: true }).forEach((entry) => {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) { walk(full); return; }
      if (!/\.jsx?$/.test(entry.name) || /\.test\.jsx?$/.test(entry.name)) return;
      if (/role=["{']+tablist/.test(fs.readFileSync(full, 'utf8'))) {
        found.push(path.relative(SRC, full).split(path.sep).join('/'));
      }
    });
  };
  walk(SRC);
  expect(found.sort()).toEqual(['components/UI/Tabs/Tabs.jsx', ...OWN_TABLIST_ALLOWED].sort());
});

// Режимы wide / compact / mobile задаёт shared ResponsiveTable; фичи на нём
// своих container queries для таблиц не пишут.
test('/admin/users: своей responsive-механики таблицы нет — только ResponsiveTable', () => {
  const dir = path.join(SRC, 'features/admin/users/components');
  fs.readdirSync(dir).filter((f) => f.endsWith('.css')).forEach((file) => {
    const css = fs.readFileSync(path.join(dir, file), 'utf8');
    expect(css).not.toMatch(/@container|container-type/);
  });
  expect(read('features/admin/users/components/UsersDataView.jsx'))
    .toMatch(/components\/UI\/ResponsiveTable\/ResponsiveTable/);
});
