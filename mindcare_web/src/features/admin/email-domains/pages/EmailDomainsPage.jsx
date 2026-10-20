import EmailDomainsSection from '../components/EmailDomainsSection';
import styles from './EmailDomainsPage.module.css';

export default function EmailDomainsPage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>Домены регистрации</h1>
      <EmailDomainsSection />
    </div>
  );
}
