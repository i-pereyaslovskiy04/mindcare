import styles from './ServiceCard.module.css';

const ACCENTS = ['accent1', 'accent2', 'accent3', 'accent4', 'accent5'];

const CheckIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true" className={styles.checkIcon}>
    <path d="M2 7l3 3L11 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export default function ServiceCard({ service, index }) {
  const accentClass = styles[ACCENTS[index % ACCENTS.length]];
  const hasImage = Boolean(service.image_url);
  const benefits = service.benefits ?? [];

  return (
    <article className={styles.card}>
      <div
        className={`${styles.cardVisual} ${accentClass} ${hasImage ? styles.hasImage : ''}`}
        style={hasImage ? { '--card-image': `url("${service.image_url}")` } : undefined}
      >
        <span className={styles.cardNum} aria-hidden="true">
          {String(index + 1).padStart(2, '0')}
        </span>
      </div>

      <div className={styles.cardContent}>
        <h3 className={styles.cardTitle}>{service.title}</h3>
        <p className={styles.cardDesc}>{service.description}</p>

        {benefits.length > 0 && (
          <ul className={styles.benefits}>
            {benefits.map((b) => (
              <li key={b} className={styles.benefit}>
                <CheckIcon />
                <span>{b}</span>
              </li>
            ))}
          </ul>
        )}

        {service.link_url && (
          <a className={styles.cardBtn} href={service.link_url}>
            Записаться
          </a>
        )}
      </div>
    </article>
  );
}
