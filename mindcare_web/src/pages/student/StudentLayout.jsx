import CabinetLayout from '../../components/CabinetLayout/CabinetLayout';

const NAV_SECTIONS = [
  {
    label: 'Самопомощь',
    items: [
      { key: 'home',      label: 'Главная',            icon: 'home',     to: '/student',           end: true },
      { key: 'diary',     label: 'Дневник состояния',  icon: 'diary',    to: '/student/diary',     end: true },
      { key: 'tests',     label: 'Тесты',              icon: 'tests',    to: '/student/tests',     end: true },
      { key: 'materials', label: 'Материалы и статьи', icon: 'articles', to: '/student/materials', end: true },
    ],
  },
  {
    label: 'Терапия',
    items: [
      { key: 'tasks',    label: 'Задания психолога',  icon: 'tasks',    to: '/student/tasks',    end: true, badge: '2' },
      { key: 'chat',     label: 'Чат с психологом',   icon: 'chat',     to: '/student/chat',     end: true, badge: '1' },
      { key: 'calendar', label: 'Календарь и сессии', icon: 'calendar', to: '/student/calendar', end: true },
    ],
  },
  {
    label: 'Аккаунт',
    items: [
      { key: 'settings', label: 'Настройки', icon: 'settings', to: '/student/settings', end: true },
    ],
  },
];

const CRUMB_LABELS = {
  '/student':           'Главная',
  '/student/diary':     'Дневник состояния',
  '/student/tests':     'Тесты',
  '/student/materials': 'Материалы и статьи',
  '/student/tasks':     'Задания психолога',
  '/student/chat':      'Чат с психологом',
  '/student/calendar':  'Календарь и сессии',
  '/student/settings':  'Настройки',
};

export default function StudentLayout() {
  return (
    <CabinetLayout
      navSections={NAV_SECTIONS}
      crumbLabels={CRUMB_LABELS}
    />
  );
}
