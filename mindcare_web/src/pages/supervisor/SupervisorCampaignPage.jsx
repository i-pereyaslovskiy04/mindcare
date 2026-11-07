import { Link, useNavigate, useParams } from 'react-router-dom';
import Icon from '../../components/Icon/Icon';
import Button from '../../components/UI/Button/Button';
import HelpButton from '../../components/HelpButton/HelpButton';
import useCampaign from '../../features/campaigns/hooks/useCampaign';
import CampaignCard from '../../features/campaigns/ui/CampaignCard';
import styles from './CampaignsPage.module.css';

/**
 * Страница одной кампании (/supervisor/campaigns/:uuid): ссылка, сроки и код,
 * результаты, статистика, участники — то, что раньше раскрывалось в ленте.
 * После удаления — возврат к списку.
 */
export default function SupervisorCampaignPage() {
  const { uuid } = useParams();
  const navigate = useNavigate();
  const { data: campaign, error, refetch, setData: setCampaign } = useCampaign(uuid);

  return (
    <div className={styles.page}>
      <div className={styles.titleRow}>
        <Link to="/supervisor/campaigns" className={styles.back}>
          <Icon name="chevron-left" size={14} /> К списку кампаний
        </Link>
        <HelpButton guide="campaigns" section="campaign-page" />
      </div>
      {error && (
        <div className={styles.errorRow}>
          <p className={styles.error} role="alert">{error}</p>
          <Button type="button" variant="secondary" onClick={refetch}>Повторить</Button>
        </div>
      )}
      {!error && !campaign && <p className={styles.muted} role="status">Загрузка…</p>}
      {campaign && (
        <CampaignCard
          campaign={campaign}
          onChange={setCampaign}
          onDeleted={() => navigate('/supervisor/campaigns')}
          asPage
        />
      )}
    </div>
  );
}
