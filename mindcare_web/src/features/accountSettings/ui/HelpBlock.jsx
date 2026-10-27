import Icon from '../../../components/Icon/Icon';
import styles from './AccountSettings.module.css';

/** Телефон доверия — рабочая ссылка tel:. Реквизиты прежние. */
export default function HelpBlock() {
  return (
    <aside className={styles.crisis} aria-labelledby="settings-help-title">
      <div className={styles.crisisIcon} aria-hidden="true">
        <Icon name="bell" size={18} />
      </div>
      <div>
        <h2 id="settings-help-title" className={styles.crisisTitle}>Помощь в кризисный момент</h2>
        <p className={styles.crisisText}>
          Если совсем плохо и нужна поддержка прямо сейчас - это нормально просить о ней.
        </p>
        <a href="tel:88002000122" className={styles.crisisLink}>
          Телефон доверия 8-800-2000-122
        </a>
      </div>
    </aside>
  );
}
