import Navbar from '../Navbar/Navbar';
import Footer from '../Footer/Footer';
import styles from './DashboardLayout.module.css';

export default function DashboardLayout({ children }) {
  return (
    <>
      <Navbar />
      <main className={styles.main}>
        {children}
      </main>
      <Footer />
    </>
  );
}
