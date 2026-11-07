import { useEffect, useRef } from 'react';
import Button from '../../../components/UI/Button/Button';
import useCampaignForm from '../hooks/useCampaignForm';
import usePublicCampaign from '../hooks/usePublicCampaign';
import CampaignCodeStep from './CampaignCodeStep';
import CampaignProfileStep from './CampaignProfileStep';
import CampaignQuestionsStep from './CampaignQuestionsStep';
import styles from './PublicCampaign.module.css';

/**
 * Прохождение тестирования по ссылке кампании без входа (ADR-036):
 * анкета и согласие → вопросы → «Спасибо». Результат участнику не
 * показывается. Черновик — в sessionStorage вкладки (переживает F5).
 * Кодовое слово (если задано) спрашивается до анкеты; до начала срока —
 * экран с датой начала.
 */

const MSK = { timeZone: 'Europe/Moscow', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' };

function formatMsk(iso) {
  return iso ? `${new Date(iso).toLocaleString('ru-RU', MSK)} (МСК)` : null;
}
export default function PublicCampaign({ token }) {
  const { data, loading, error, refetch, accessCode, unlock, forgetCode } = usePublicCampaign(token);
  const form = useCampaignForm(token, data, {
    onConsentOutdated: refetch, accessCode, onAccessCodeRejected: forgetCode,
  });
  const locked = Boolean(data?.access_code_required && !data.questions.length);
  const headingRef = useRef(null);

  // Смена шага — фокус на заголовке (экранные дикторы узнают о переходе).
  useEffect(() => {
    if (data) headingRef.current?.focus();
  }, [form.step, data, locked]);

  if (loading && !data) {
    return <p className={styles.status} role="status">Загрузка…</p>;
  }

  if (error?.code === 'campaign_not_started') {
    return (
      <section className={styles.state}>
        <h1 className={styles.title}>Тестирование ещё не началось</h1>
        <p className={styles.text}>
          {error.opensAt
            ? `Начало: ${formatMsk(error.opensAt)}. Откройте ссылку в это время.`
            : 'Откройте ссылку позже.'}
        </p>
        <Button type="button" onClick={refetch}>Проверить снова</Button>
      </section>
    );
  }

  if (error) {
    const notFound = error.status === 404;
    return (
      <section className={styles.state}>
        <h1 className={styles.title}>
          {notFound ? 'Опрос недоступен' : 'Не удалось открыть опрос'}
        </h1>
        <p className={styles.text}>
          {notFound
            ? 'Ссылка недействительна или опрос уже завершён. Уточните ссылку у организаторов.'
            : 'Проверьте соединение с интернетом и попробуйте ещё раз.'}
        </p>
        {!notFound && (
          <Button type="button" onClick={refetch}>Повторить</Button>
        )}
      </section>
    );
  }

  if (!data) return null;

  if (form.step === 'done') {
    return (
      <section className={styles.state}>
        <h1 ref={headingRef} tabIndex={-1} className={styles.title}>
          Спасибо за участие!
        </h1>
        <p className={styles.text}>
          Ваши ответы отправлены. Результаты обработает психологическая служба
          университета. Эту страницу можно закрыть.
        </p>
      </section>
    );
  }

  if (locked) {
    return (
      <div className={styles.wrap}>
        <header className={styles.header}>
          <p className={styles.kicker}>{data.test_title}</p>
          <h1 ref={headingRef} tabIndex={-1} className={styles.title}>{data.title}</h1>
        </header>
        <CampaignCodeStep unlock={unlock} notice={form.submitError} />
      </div>
    );
  }

  const stepLabel = form.step === 'profile' ? 'Шаг 1 из 2. Анкета' : 'Шаг 2 из 2. Вопросы';
  const closesAt = formatMsk(data.closes_at);

  return (
    <div className={styles.wrap}>
      <header className={styles.header}>
        <p className={styles.kicker}>{data.test_title}</p>
        <h1 ref={headingRef} tabIndex={-1} className={styles.title}>{data.title}</h1>
        <p className={styles.step}>{stepLabel}</p>
        {closesAt && <p className={styles.kicker}>Пройти можно до {closesAt}</p>}
      </header>
      {form.step === 'profile'
        ? <CampaignProfileStep campaign={data} form={form} />
        : <CampaignQuestionsStep campaign={data} form={form} />}
    </div>
  );
}
