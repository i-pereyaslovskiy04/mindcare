import { Link } from "react-router-dom";
import styles from "./NotFound.module.css";

export default function NotFound() {
  return (
    <div className={styles.page}>
      <h1>404</h1>
      <p>Страница не найдена</p>
      <Link to="/" className={styles.link}>На главную</Link>
    </div>
  );
}
