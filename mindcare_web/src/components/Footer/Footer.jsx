import styles from './Footer.module.css';
import { TelegramIcon, VKIcon, YandexIcon } from '../icons';

const SOCIAL_COLOR = 'rgba(139,111,71,0.7)';

const SOCIALS = [
  { name: 'ВКонтакте', href: '#', Icon: VKIcon },
  { name: 'Telegram', href: '#', Icon: TelegramIcon },
  { name: 'Яндекс', href: '#', Icon: YandexIcon },
];

const NAV_LINKS = [
  { label: 'Главная', href: '/' },
  { label: 'О нас', href: '/about' },
  { label: 'Услуги', href: '/services' },
  { label: 'Материалы', href: '/materials' },
];

export default function Footer() {
  return (
    <footer className={styles.footer}>
      <div className="container">
        <div className={styles.footerTop}>
          <div className={styles.footerBrand}>
            <div className={styles.brandName}>
              Психо<span className={styles.brandNameHighlight}>логия</span> ДонГУ
            </div>
            <div className={styles.brandDesc}>
              Центр психологической помощи при Донецком государственном университете.
            </div>
            <a className={styles.mailLink} href="mailto:support@donnu.ru">
              support@donnu.ru
            </a>
          </div>

          <div>
            <div className={styles.colLabel}>Навигация</div>
            <ul className={styles.navList}>
              {NAV_LINKS.map(({ label, href }) => (
                <li key={label}>
                  <a href={href}>{label}</a>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <div className={styles.colLabel}>Мы в соцсетях</div>
            <div className={styles.socials}>
              {SOCIALS.map(({ name, href, Icon }) => (
                <a key={name} className={styles.socRow} href={href} aria-label={name}>
                  <div className={styles.socIcon}>
                    <Icon color={SOCIAL_COLOR} />
                  </div>
                  <span className={styles.socName}>{name}</span>
                </a>
              ))}
            </div>
          </div>
        </div>

        <div className={styles.legal}>
          <div className={styles.copy}>
            © ФГБОУ ВО «Донецкий государственный университет» 2026
          </div>
          <div className={styles.legalLinks}>
            <a className={styles.legalLink} href="/privacy-policy">
              Политика персональных данных
            </a>
            <a className={styles.legalLink} href="/cookies-policy">
              Политика cookies
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
