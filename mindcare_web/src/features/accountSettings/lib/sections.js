import { STUDENT_VERIFICATION_ANCHOR } from '../../studentVerification/lib/status';

export const SECTION_PERSONAL = 'personal';
export const SECTION_CONTACTS = 'contacts';
export const SECTION_SECURITY = 'security';

export const SETTINGS_SECTIONS = [
  { id: SECTION_PERSONAL, label: 'Личные данные' },
  { id: SECTION_CONTACTS, label: 'Контакты' },
  { id: SECTION_SECURITY, label: 'Безопасность' },
];

const HASH_TO_SECTION = {
  [STUDENT_VERIFICATION_ANCHOR]: SECTION_PERSONAL,   // ссылка из system-сообщения
  [SECTION_PERSONAL]: SECTION_PERSONAL,
  [SECTION_CONTACTS]: SECTION_CONTACTS,
  [SECTION_SECURITY]: SECTION_SECURITY,
};

/** Раздел, на который указывает hash (`#contacts`), либо null, если hash не наш. */
export function sectionFromHash(hash) {
  const key = (hash || '').replace(/^#/, '');
  return HASH_TO_SECTION[key] ?? null;
}
