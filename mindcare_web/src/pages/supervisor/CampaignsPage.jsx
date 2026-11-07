import { useNavigate } from 'react-router-dom';
import Button from '../../components/UI/Button/Button';
import HelpButton from '../../components/HelpButton/HelpButton';
import useCampaigns from '../../features/campaigns/hooks/useCampaigns';
import CampaignCreateForm from '../../features/campaigns/ui/CampaignCreateForm';
import CampaignsTable, { campaignPath } from '../../features/campaigns/ui/CampaignsTable';
import styles from './CampaignsPage.module.css';

/**
 * «Тестирование по ссылке» (ADR-036): кампании супервизора — одна ссылка на
 * всех участников без регистрации, выгрузка результатов в xlsx. Доступен и
 * администратору «под именем» супервизора: backend пишет в события кампаний
 * impersonator_user_id (ADR-036, дополнение 2026-11-05).
 * Список — компактные строки; кампания открывается на своей странице.
 */
export default function CampaignsPage() {
  const list = useCampaigns();
  const navigate = useNavigate();

  return (
    <div className={styles.page}>
      <div className={styles.intro}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>Тестирование по ссылке</h1>
          <HelpButton guide="campaigns" />
        </div>
        <p className={styles.muted}>
          Создайте кампанию и отправьте ссылку студентам: они проходят методику без
          регистрации, указав ФИО, факультет, специальность, возраст и пол. Результат
          участникам не показывается — скачайте готовую таблицу в xlsx.
        </p>
      </div>

      <CampaignCreateForm onCreated={(c) => navigate(campaignPath(c.uuid))} />

      <section className={styles.list} aria-labelledby="campaigns-list-title">
        <h2 id="campaigns-list-title" className={styles.subtitle}>Кампании</h2>
        {list.error && (
          <div className={styles.errorRow}>
            <p className={styles.error} role="alert">{list.error}</p>
            <Button type="button" variant="secondary" onClick={list.refetch}>Повторить</Button>
          </div>
        )}
        {!list.error && <CampaignsTable items={list.items} loading={list.loading} />}
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
