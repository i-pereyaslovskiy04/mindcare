import CabinetLayout from '../../components/CabinetLayout/CabinetLayout';

const NAV_SECTIONS = [
  {
    label: 'Работа',
    items: [
      { key: 'home',      label: 'Главная',         icon: 'home',     to: '/psychologist',          end: true,  disabled: false },
      { key: 'clients',   label: 'Клиенты',         icon: 'users',    to: '/psychologist/clients',             disabled: true  },
      { key: 'sessions',  label: 'Сессии',          icon: 'calendar', to: '/psychologist/sessions',            disabled: true  },
      { key: 'chat',      label: 'Чат с клиентами', icon: 'chat',     to: '/psychologist/chat',                disabled: true  },
      { key: 'materials', label: 'Материалы',       icon: 'articles', to: '/psychologist/materials',           disabled: true  },
    ],
  },
  {
    label: 'Аккаунт',
    items: [
      { key: 'settings',  label: 'Настройки',       icon: 'settings', to: '/psychologist/settings',            disabled: false },
    ],
  },
];

const CRUMB_LABELS = {
  '/psychologist':          'Главная',
  '/psychologist/settings': 'Настройки',
};

export default function PsychologistLayout() {
  return <CabinetLayout navSections={NAV_SECTIONS} crumbLabels={CRUMB_LABELS} />;
}
