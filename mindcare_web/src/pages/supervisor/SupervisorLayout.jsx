import CabinetLayout from '../../components/CabinetLayout/CabinetLayout';

const NAV_SECTIONS = [
  {
    label: 'Супервизия',
    items: [
      { key: 'home',          label: 'Главная',              icon: 'home',     to: '/supervisor',                    end: true,  disabled: false },
      { key: 'engagements',   label: 'Назначение психологов', icon: 'tasks',   to: '/supervisor/engagements',        end: true,  disabled: false },
      { key: 'meeting-types', label: 'Типы встреч',          icon: 'calendar', to: '/supervisor/meeting-types',      end: true,  disabled: false },
      { key: 'schedule',      label: 'Расписание',           icon: 'calendar', to: '/supervisor/schedule',           end: true,  disabled: false },
      { key: 'booking',       label: 'Запись',               icon: 'calendar', to: '/supervisor/booking',            end: true,  disabled: false },
      { key: 'group-sessions',label: 'Групповые занятия',    icon: 'users',    to: '/supervisor/group-sessions',     end: true,  disabled: false },
      { key: 'psych',         label: 'Психологи',            icon: 'users',    to: '/supervisor/psychologists',                  disabled: true  },
      { key: 'reports',       label: 'Отчёты',               icon: 'articles', to: '/supervisor/reports',                        disabled: true  },
    ],
  },
  {
    label: 'Аккаунт',
    items: [
      { key: 'settings', label: 'Настройки', icon: 'settings', to: '/supervisor/settings', disabled: false },
    ],
  },
];

const CRUMB_LABELS = {
  '/supervisor':                  'Главная',
  '/supervisor/engagements':      'Назначение психологов',
  '/supervisor/meeting-types':    'Типы встреч',
  '/supervisor/schedule':         'Расписание',
  '/supervisor/booking':          'Запись',
  '/supervisor/group-sessions':   'Групповые занятия',
  '/supervisor/settings':         'Настройки',
};

export default function SupervisorLayout() {
  return <CabinetLayout cabinetRole="supervisor" navSections={NAV_SECTIONS} crumbLabels={CRUMB_LABELS} />;
}
