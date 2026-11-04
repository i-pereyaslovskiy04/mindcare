import { useEffect, useRef } from 'react';
import Button from '../../../components/UI/Button/Button';
import useCampaignForm from '../hooks/useCampaignForm';
import usePublicCampaign from '../hooks/usePublicCampaign';
import CampaignProfileStep from './CampaignProfileStep';
import CampaignQuestionsStep from './CampaignQuestionsStep';
import styles from './PublicCampaign.module.css';

/**
 * Прохождение тестирования по ссылке кампании без входа (ADR-036):
 * анкета и согласие → вопросы → «Спасибо». Результат участнику не
 * показывается. Черновик — в sessionStorage вкладки (переживает F5).
 */
export default function PublicCampaign({ token }) {
  const { data, loading, error, refetch } = usePublicCampaign(token);
  const form = useCampaignForm(token, data, { onConsentOutdated: refetch });
  const headingRef = useRef(null);

  // Смена шага — фокус на заголовке (экранные дикторы узнают о переходе).
  useEffect(() => {
    if (data) headingRef.current?.focus();
  }, [form.step, data]);

  if (loading && !data) {
    return <p className={styles.status} role="status">Загрузка…</p>;
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

  const stepLabel = form.step === 'profile' ? 'Шаг 1 из 2. Анкета' : 'Шаг 2 из 2. Вопросы';

  return (
    <div className={styles.wrap}>
      <header className={styles.header}>
        <p className={styles.kicker}>{data.test_title}</p>
        <h1 ref={headingRef} tabIndex={-1} className={styles.title}>{data.title}</h1>
        <p className={styles.step}>{stepLabel}</p>
      </header>
      {form.step === 'profile'
        ? <CampaignProfileStep campaign={data} form={form} />
        : <CampaignQuestionsStep campaign={data} form={form} />}
    </div>
  );
}
