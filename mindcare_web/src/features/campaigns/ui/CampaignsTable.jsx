import { Link } from 'react-router-dom';
import Badge from '../../../components/UI/Badge/Badge';
import ButtonLink from '../../../components/UI/Button/ButtonLink';
import ResponsiveTable from '../../../components/UI/ResponsiveTable/ResponsiveTable';
import { LINK_STATE, formatDate, formatMsk } from './CampaignCard';
import styles from './CampaignsTable.module.css';

export const campaignPath = (uuid) => `/supervisor/campaigns/${uuid}`;

function stateOf(c) {
  return LINK_STATE[c.link_state] || LINK_STATE[c.status === 'open' ? 'open' : 'closed'];
}

/**
 * Список кампаний — компактные строки (название, методика, состояние ссылки,
 * число прохождений). Всё остальное — на странице кампании (campaignPath).
 */
export default function CampaignsTable({ items, loading, error }) {
  return (
    <ResponsiveTable
      label="Кампании"
      items={items}
      getKey={(c) => c.uuid}
      loading={loading}
      error={error}
      emptyText="Кампаний пока нет."
      identity={{
        header: 'Кампания',
        primary: (c) => <Link className={styles.title} to={campaignPath(c.uuid)}>{c.title}</Link>,
        secondary: (c) => (
          <>
            {c.test_title}
            <span aria-hidden="true"> · </span>
            <span className={styles.nowrap}>создана {formatDate(c.created_at)}</span>
          </>
        ),
      }}
      status={{
        header: 'Ссылка',
        render: (c) => {
          const st = stateOf(c);
          return (
            <>
              <Badge tone={st.tone}>{st.label}</Badge>
              {c.access_code_set && <Badge tone="neutral">Кодовое слово</Badge>}
              {c.closes_at && c.link_state === 'open' && (
                <Badge tone="neutral">{`до ${formatMsk(c.closes_at)}`}</Badge>
              )}
            </>
          );
        },
      }}
      columns={[{
        key: 'count', header: 'Прошли', width: '7rem',
        render: (c) => <span className={styles.count}>{c.responses_count}</span>,
      }]}
      meta={(c) => [{ label: 'Прошли', value: c.responses_count }]}
      actions={{
        primary: (c) => (
          <ButtonLink to={campaignPath(c.uuid)} variant="secondary" size="sm"
            aria-label={`Открыть кампанию «${c.title}»`}>
            Открыть
          </ButtonLink>
        ),
      }}
    />
  );
}
