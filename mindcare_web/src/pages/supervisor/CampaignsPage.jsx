import Button from '../../components/UI/Button/Button';
import { useAuth } from '../../features/auth/AuthContext';
import useCampaigns from '../../features/campaigns/hooks/useCampaigns';
import CampaignCard from '../../features/campaigns/ui/CampaignCard';
import CampaignCreateForm from '../../features/campaigns/ui/CampaignCreateForm';
import styles from './CampaignsPage.module.css';

/**
 * «Тестирование по ссылке» (ADR-036): кампании супервизора — одна ссылка на
 * всех участников без регистрации, выгрузка результатов в xlsx. В режиме
 * «под именем» раздел недоступен (backend отвечает 403) — запросов нет.
 */
export default function CampaignsPage() {
  const { isImpersonating } = useAuth();
  const list = useCampaigns(!isImpersonating);

  if (isImpersonating) {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>Тестирование по ссылке</h1>
        <p className={styles.muted}>Раздел недоступен при входе под именем пользователя.</p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.intro}>
        <h1 className={styles.title}>Тестирование по ссылке</h1>
        <p className={styles.muted}>
          Создайте кампанию и отправьте ссылку студентам: они проходят методику без
          регистрации, указав ФИО, факультет, специальность, возраст и пол. Результат
          участникам не показывается — скачайте готовую таблицу в xlsx.
        </p>
      </div>

      <CampaignCreateForm onCreated={list.replaceItem} />

      <section className={styles.list} aria-labelledby="campaigns-list-title">
        <h2 id="campaigns-list-title" className={styles.subtitle}>Кампании</h2>
        {list.loading && <p className={styles.muted} role="status">Загрузка…</p>}
        {list.error && (
          <div className={styles.errorRow}>
            <p className={styles.error} role="alert">{list.error}</p>
            <Button type="button" variant="secondary" onClick={list.refetch}>Повторить</Button>
          </div>
        )}
        {!list.loading && !list.error && !list.items.length && (
          <p className={styles.muted}>Кампаний пока нет.</p>
        )}
        {list.items.map((c) => (
          <CampaignCard
            key={c.uuid}
            campaign={c}
            onChange={list.replaceItem}
            onDeleted={list.removeItem}
          />
        ))}
        {list.hasMore && (
          <Button type="button" variant="secondary" onClick={list.loadMore}
            loading={list.loadingMore}>
            Показать ещё
          </Button>
        )}
      </section>
    </div>
  );
}
