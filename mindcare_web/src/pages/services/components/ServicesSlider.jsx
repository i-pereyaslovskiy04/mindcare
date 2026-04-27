import { useRef, useState, useEffect, useCallback } from 'react';
import ServiceCard from './ServiceCard';
import styles from './ServicesSlider.module.css';

const SERVICES = [
  {
    id: 1,
    title: 'Психологическое консультирование',
    description: 'Индивидуальная работа с психологом — онлайн или офлайн. Помогаем разобраться в трудностях, снять тревогу и найти эффективный выход из сложных ситуаций.',
    benefits: [
      'Разобраться в своей ситуации',
      'Выявить причины проблемы',
      'Найти конкретные пути выхода',
      'Восстановить психологический комфорт',
    ],
  },
  {
    id: 2,
    title: 'Психодиагностика',
    description: 'Комплексная оценка психологического состояния на современном оборудовании с сертифицированными методиками и подробным разбором результатов с психологом.',
    benefits: [
      'Оценка памяти, внимания и мышления',
      'Уровень интеллектуального развития',
      'Эмоционально-волевые качества',
      'Личностные черты и мотивация',
    ],
  },
  {
    id: 3,
    title: 'Социально-психологические тренинги',
    description: 'Групповые занятия в безопасной обстановке — для тех, кто хочет лучше понимать себя и других, развить навыки общения и управления эмоциями.',
    benefits: [
      'Лучше понимать других людей',
      'Узнать себя глубже',
      'Управлять эмоциями и реакциями',
      'Приобрести новые навыки общения',
    ],
  },
  {
    id: 4,
    title: 'Профориентация',
    description: 'Помогаем выявить сильные стороны и склонности, выбрать профессиональный путь и построить карьерный план — для студентов, абитуриентов и сотрудников.',
    benefits: [
      'Диагностика профессиональных склонностей',
      'Анализ ваших сильных сторон',
      'Построение карьерного плана',
      'Знакомство с профессиограммами',
    ],
  },
  {
    id: 5,
    title: 'Супервизия и обучение',
    description: 'Постоянное развитие специалистов под руководством опытных наставников — чтобы каждый клиент получал помощь самого высокого профессионального уровня.',
    benefits: [
      'Супервизия у опытных психологов',
      'Курсы повышения квалификации',
      'Участие в профессиональных конференциях',
      'Освоение современных методик',
    ],
  },
];

const ArrowIcon = ({ dir }) => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
    <path
      d={dir === 'left' ? 'M11 4L6 9l5 5' : 'M7 4l5 5-5 5'}
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export default function ServicesSlider() {
  const trackRef = useRef(null);
  const [canPrev, setCanPrev] = useState(false);
  const [canNext, setCanNext] = useState(false);

  const syncArrows = useCallback(() => {
    const t = trackRef.current;
    if (!t) return;
    setCanPrev(t.scrollLeft > 4);
    setCanNext(t.scrollLeft < t.scrollWidth - t.clientWidth - 4);
  }, []);

  useEffect(() => {
    syncArrows();
    window.addEventListener('resize', syncArrows);
    return () => window.removeEventListener('resize', syncArrows);
  }, [syncArrows]);

  const scroll = (dir) => {
    const track = trackRef.current;
    if (!track || !track.children.length) return;
    const card = track.children[0];
    const gap = parseFloat(getComputedStyle(track).columnGap) || 18;
    track.scrollBy({ left: dir * (card.offsetWidth + gap), behavior: 'smooth' });
  };

  return (
    <div className={styles.slider}>
      <div className={styles.sliderHeader}>
        <h2 className={styles.sliderTitle}>Наши услуги</h2>
        <div className={styles.arrows}>
          <button
            className={`${styles.arrow} ${!canPrev ? styles.arrowOff : ''}`}
            onClick={() => scroll(-1)}
            disabled={!canPrev}
            aria-label="Предыдущие услуги"
            type="button"
          >
            <ArrowIcon dir="left" />
          </button>
          <button
            className={`${styles.arrow} ${!canNext ? styles.arrowOff : ''}`}
            onClick={() => scroll(1)}
            disabled={!canNext}
            aria-label="Следующие услуги"
            type="button"
          >
            <ArrowIcon dir="right" />
          </button>
        </div>
      </div>

      <div
        className={styles.sliderTrack}
        ref={trackRef}
        onScroll={syncArrows}
      >
        {SERVICES.map((service, i) => (
          <ServiceCard key={service.id} service={service} index={i} />
        ))}
      </div>
    </div>
  );
}
