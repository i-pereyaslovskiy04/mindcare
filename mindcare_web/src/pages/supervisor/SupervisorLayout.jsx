import CabinetLayout from '../../components/CabinetLayout/CabinetLayout';

const NAV_SECTIONS = [
  {
    label: 'Супервизия',
    items: [
      { key: 'home',     label: 'Главная',              icon: 'home',     to: '/supervisor',               end: true,  disabled: false },
      { key: 'psych',    label: 'Психологи',            icon: 'users',    to: '/supervisor/psychologists',             disabled: true  },
      { key: 'sessions', label: 'Сессии супервизии',    icon: 'calendar', to: '/supervisor/sessions',                  disabled: true  },
      { key: 'reports',  label: 'Отчёты',               icon: 'articles', to: '/supervisor/reports',                   disabled: true  },
    ],
  },
  {
    label: 'Аккаунт',
    items: [
      { key: 'settings', label: 'Настройки',            icon: 'settings', to: '/supervisor/settings',                  disabled: false },
    ],
  },
];

const CRUMB_LABELS = {
  '/supervisor':          'Главная',
  '/supervisor/settings': 'Настройки',
};

export default function SupervisorLayout() {
  return <CabinetLayout navSections={NAV_SECTIONS} crumbLabels={CRUMB_LABELS} />;
}
