import { Link } from 'react-router-dom';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import styles from './NotFound.module.css';

export default function NotFound() {
  return (
    <>
      <Navbar />
      <div className={styles.wrap}>
        <p className={styles.code}>404</p>
        <h1 className={styles.title}>Страница не найдена</h1>
        <p className={styles.sub}>Возможно, адрес изменился или страница была удалена.</p>
        <Link to="/" className={styles.link}>Вернуться на главную</Link>
      </div>
      <Footer />
    </>
  );
}
