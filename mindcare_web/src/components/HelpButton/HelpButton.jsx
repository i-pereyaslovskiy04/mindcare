import Icon from '../Icon/Icon';
import buttonStyles from '../UI/Button/Button.module.css';
import styles from './HelpButton.module.css';

/** Руководства — статические страницы public/help/<guide>.html (с PDF). */
export const HELP_GUIDES = {
  campaigns: 'Тестирование по ссылке',
  methodologies: 'Методики',
  participant: 'Памятка участнику',
};

export function helpHref(guide, section) {
  return `/help/${guide}.html${section ? `#${section}` : ''}`;
}

/**
 * Кнопка «Справка»: открывает страницу руководства (там же — PDF) в новой
 * вкладке, чтобы не терять заполненную форму. section — якорь раздела.
 * variant="link" — текстовая ссылка (для публичных страниц).
 */
export default function HelpButton({ guide, section, label = 'Справка', variant = 'button' }) {
  const title = `Руководство «${HELP_GUIDES[guide] || 'Справка'}» — откроется в новой вкладке`;
  const cls = variant === 'link'
    ? styles.link
    : [buttonStyles.btn, buttonStyles.secondary, buttonStyles.sm, styles.button].join(' ');
  return (
    <a className={cls} href={helpHref(guide, section)} target="_blank" rel="noopener noreferrer"
      title={title}>
      <Icon name="info" size={16} />
      <span>{label}</span>
      <span className={styles.srOnly}> (откроется в новой вкладке)</span>
    </a>
  );
}
