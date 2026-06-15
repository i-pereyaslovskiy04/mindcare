import styles from './Tag.module.css';

const VARIANT_CLASS = {
  public:   styles.public,
  admin:    styles.admin,
  category: styles.category,
  card:     styles.card,
};

export default function Tag({ variant = 'public', className, children, title }) {
  const cls = [styles.tag, VARIANT_CLASS[variant] ?? styles.public, className]
    .filter(Boolean)
    .join(' ');

  return (
    <span className={cls} title={title}>
      {children}
    </span>
  );
}
