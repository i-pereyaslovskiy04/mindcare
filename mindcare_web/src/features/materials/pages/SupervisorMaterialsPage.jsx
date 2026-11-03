import { useState } from 'react';
import Tabs, { tabButtonId, tabPanelId } from '../../../components/UI/Tabs/Tabs';
import { useAuth } from '../../auth/AuthContext';
import ArticleReview from '../ui/ArticleReview';
import MyArticles from '../ui/MyArticles';
import styles from './MaterialsReviewPage.module.css';

const TABS_PREFIX = 'supervisor-materials';
const TABS = [
  { id: 'review', label: 'На проверке' },
  { id: 'mine', label: 'Мои материалы' },
];

/**
 * Материалы супервизора (/supervisor/materials): очередь модерации статей
 * психологов (ADR-034) и свои материалы — супервизор публикует их сам, без
 * очереди (Дополнение 2026-10-28). Обе вкладки закрыты в режиме «под именем»
 * (backend отвечает 403) — тогда показывается пояснение без запросов.
 */
export default function SupervisorMaterialsPage() {
  const { isImpersonating } = useAuth();
  const [active, setActive] = useState('review');

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>Материалы</h1>
      <p className={styles.pageSub}>
        Статьи психологов, отправленные на проверку, и ваши собственные материалы. Свои
        материалы вы публикуете сами; при возврате на доработку автор увидит ваш комментарий.
      </p>

      {isImpersonating ? (
        <p className={styles.pageSub}>Материалы недоступны при входе под именем пользователя.</p>
      ) : (
        <>
          <Tabs
            tabs={TABS}
            active={active}
            onChange={setActive}
            label="Разделы материалов"
            idPrefix={TABS_PREFIX}
            fill
            className={styles.tabs}
          />
          <div
            role="tabpanel"
            id={tabPanelId(TABS_PREFIX, 'review')}
            aria-labelledby={tabButtonId(TABS_PREFIX, 'review')}
            hidden={active !== 'review'}
          >
            {active === 'review' && <ArticleReview />}
          </div>
          <div
            role="tabpanel"
            id={tabPanelId(TABS_PREFIX, 'mine')}
            aria-labelledby={tabButtonId(TABS_PREFIX, 'mine')}
            hidden={active !== 'mine'}
          >
            {active === 'mine' && <MyArticles role="supervisor" />}
          </div>
        </>
      )}
    </div>
  );
}
