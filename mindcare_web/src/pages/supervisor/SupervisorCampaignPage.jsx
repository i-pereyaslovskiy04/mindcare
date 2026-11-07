import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getCampaign } from '../../api/campaigns.api';
import Icon from '../../components/Icon/Icon';
import Button from '../../components/UI/Button/Button';
import HelpButton from '../../components/HelpButton/HelpButton';
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
  const [campaign, setCampaign] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setError(null);
    getCampaign(uuid)
      .then(setCampaign)
      .catch((err) => setError(err?.status === 404
        ? 'Кампания не найдена — возможно, её удалили.'
        : err?.message || 'Не удалось загрузить кампанию'));
  }, [uuid]);

  useEffect(() => { setCampaign(null); load(); }, [load]);

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
          <Button type="button" variant="secondary" onClick={load}>Повторить</Button>
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
