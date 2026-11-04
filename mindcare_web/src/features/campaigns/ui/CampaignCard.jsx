import { useId, useState } from 'react';
import {
  deleteCampaign, downloadCampaignResults, rotateCampaignLink, setCampaignStatus,
} from '../../../api/campaigns.api';
import { saveBlobToDisk } from '../../../api/client';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import ConfirmDialog from '../../assignments/ui/ConfirmDialog';
import CampaignResponses from './CampaignResponses';
import CampaignResults from './CampaignResults';
import styles from './CampaignCard.module.css';

export function campaignLink(campaign) {
  if (campaign.link_url) return campaign.link_url;
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  return `${origin}${campaign.link_path}`;
}

export function exportFilename(title) {
  const safe = String(title || 'кампания').replace(/[\\/:*?"<>|\s]+/g, '_').slice(0, 80);
  return `Результаты_${safe}.xlsx`;
}

function formatDate(value) {
  return value ? new Date(value).toLocaleDateString('ru-RU') : '';
}

const DIALOGS = {
  rotate: {
    title: 'Выпустить новую ссылку?',
    description: 'Старая ссылка сразу перестанет работать. Уже полученные ответы сохранятся.',
    confirmLabel: 'Выпустить',
    tone: 'primary',
  },
  delete: {
    title: 'Удалить кампанию?',
    description: 'Кампания, все ответы участников и записи их согласий будут удалены безвозвратно. Перед удалением скачайте результаты.',
    confirmLabel: 'Удалить',
    tone: 'danger',
  },
};

/**
 * Кампания: статус, ссылка (копировать), скачать xlsx, закрыть/открыть,
 * новая ссылка, участники, удаление. Без оптимистичного успеха: карточка
 * обновляется ответом backend (onChange) или удаляется (onDeleted).
 */
export default function CampaignCard({ campaign, onChange, onDeleted }) {
  const baseId = useId();
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [dialogError, setDialogError] = useState(null);
  // Открытая панель: null | 'results' | 'responses'.
  const [panel, setPanel] = useState(null);
  const togglePanel = (name) => setPanel((p) => (p === name ? null : name));
  const link = campaignLink(campaign);
  const isOpen = campaign.status === 'open';

  async function run(name, action) {
    setBusy(name);
    setError(null);
    setMessage(null);
    try {
      await action();
    } catch (err) {
      if (err?.name !== 'AbortError') setError(err?.message || 'Не удалось выполнить действие');
    } finally {
      setBusy(null);
    }
  }

  function copyLink() {
    run('copy', async () => {
      await navigator.clipboard.writeText(link);
      setMessage('Ссылка скопирована');
    });
  }

  function toggleStatus() {
    run('status', async () => {
      onChange(await setCampaignStatus(campaign.uuid, isOpen ? 'closed' : 'open'));
      setMessage(isOpen ? 'Кампания закрыта — ссылка больше не принимает ответы' : 'Кампания снова открыта');
    });
  }

  function download() {
    run('download', async () => {
      await saveBlobToDisk(async () => {
        const { blob } = await downloadCampaignResults(campaign.uuid);
        return blob;
      }, exportFilename(campaign.title));
    });
  }

  async function confirmDialog() {
    setBusy(dialog);
    setDialogError(null);
    try {
      if (dialog === 'rotate') {
        onChange(await rotateCampaignLink(campaign.uuid));
        setMessage('Выпущена новая ссылка — отправьте её участникам');
        setDialog(null);
      } else {
        await deleteCampaign(campaign.uuid);
        setDialog(null);
        onDeleted(campaign.uuid);
      }
    } catch (err) {
      setDialogError(err?.message || 'Не удалось выполнить действие');
    } finally {
      setBusy(null);
    }
  }

  const titleId = `${baseId}-title`;
  const linkId = `${baseId}-link`;
  const current = dialog ? DIALOGS[dialog] : null;

  return (
    <article className={styles.card} aria-labelledby={titleId}>
      <header className={styles.header}>
        <div className={styles.headText}>
          <h3 id={titleId} className={styles.title}>{campaign.title}</h3>
          <p className={styles.meta}>
            {campaign.test_title} · создана {formatDate(campaign.created_at)}
            {campaign.closed_at && ` · закрыта ${formatDate(campaign.closed_at)}`}
          </p>
        </div>
        <Badge tone={isOpen ? 'success' : 'neutral'}>{isOpen ? 'Открыта' : 'Закрыта'}</Badge>
      </header>

      <div className={styles.linkRow}>
        <label htmlFor={linkId} className={styles.linkLabel}>Ссылка для участников</label>
        <div className={styles.linkControls}>
          <input id={linkId} className={styles.linkInput} value={link} readOnly
            onFocus={(e) => e.target.select()} />
          <Button type="button" variant="secondary" onClick={copyLink}
            loading={busy === 'copy'}>
            Копировать
          </Button>
        </div>
      </div>

      <p className={styles.count}>Прошли тестирование: <strong>{campaign.responses_count}</strong></p>

      <div className={styles.actions}>
        <Button type="button" onClick={download} loading={busy === 'download'}
          disabled={!campaign.responses_count}>
          Скачать xlsx
        </Button>
        <Button type="button" variant="secondary" onClick={() => togglePanel('results')}
          aria-expanded={panel === 'results'} disabled={!campaign.responses_count}>
          {panel === 'results' ? 'Скрыть результаты' : 'Результаты'}
        </Button>
        <Button type="button" variant="secondary" onClick={() => togglePanel('responses')}
          aria-expanded={panel === 'responses'}>
          {panel === 'responses' ? 'Скрыть участников' : 'Участники'}
        </Button>
        <Button type="button" variant="secondary" onClick={toggleStatus}
          loading={busy === 'status'}>
          {isOpen ? 'Закрыть' : 'Открыть снова'}
        </Button>
        <Button type="button" variant="ghost"
          onClick={() => { setDialogError(null); setDialog('rotate'); }}>
          Новая ссылка
        </Button>
        <Button type="button" variant="danger"
          onClick={() => { setDialogError(null); setDialog('delete'); }}>
          Удалить
        </Button>
      </div>

      <div aria-live="polite" className={styles.message}>{message}</div>
      {error && <p className={styles.error} role="alert">{error}</p>}

      {panel === 'results' && (
        <div className={styles.responses}>
          <CampaignResults campaignUuid={campaign.uuid} />
        </div>
      )}

      {panel === 'responses' && (
        <div className={styles.responses}>
          <CampaignResponses
            campaignUuid={campaign.uuid}
            onDeleted={() => onChange({
              ...campaign, responses_count: Math.max(0, campaign.responses_count - 1),
            })}
          />
        </div>
      )}

      <ConfirmDialog
        open={Boolean(current)}
        title={current?.title}
        description={current?.description}
        confirmLabel={current?.confirmLabel}
        confirmTone={current?.tone}
        loading={busy === dialog && Boolean(dialog)}
        error={dialogError}
        onConfirm={confirmDialog}
        onClose={() => setDialog(null)}
      />
    </article>
  );
}
