import ArticleReview from '../ui/ArticleReview';
import styles from './MaterialsReviewPage.module.css';

/**
 * Модерация материалов психологов (ADR-034): /admin/materials-review. У
 * супервизора та же очередь — вкладка «На проверке» SupervisorMaterialsPage.
 */
export default function MaterialsReviewPage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>Модерация материалов</h1>
      <p className={styles.pageSub}>
        Статьи психологов, отправленные на проверку. Опубликованный материал появится в
        библиотеке на сайте и в кабинетах; при возврате автор увидит ваш комментарий.
      </p>
      <ArticleReview />
    </div>
  );
}
