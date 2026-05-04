import { useState, useEffect, useRef, useCallback } from 'react';
import styles from './Hero.module.css';

const SLIDES = [
  {
    label: 'Психологическая служба · ДонГУ',
    title: 'Забота о вашей',
    highlight: 'душевной гармонии',
    sub: 'Профессиональная психологическая поддержка студентов и сотрудников Донецкого государственного университета.',
  },
  {
    label: 'Поддержка и развитие',
    title: 'Ты не один',
    highlight: 'на своём пути',
    sub: 'Помогаем справляться с тревогой, стрессом и трудностями студенческой жизни в безопасном пространстве.',
  },
  {
    label: 'Запись на консультацию',
    title: 'Сделай первый',
    highlight: 'шаг к себе',
    sub: 'Доверительная беседа с опытным психологом — конфиденциально и без осуждения.',
  },
];

const INTERVAL_MS = 5000;

export default function Hero() {
  const [activeIndex, setActiveIndex] = useState(0);
  const intervalRef = useRef(null);

  // Always clears the previous interval before starting a new one — no drift possible.
  const start = useCallback(() => {
    clearInterval(intervalRef.current);
    intervalRef.current = setInterval(
      () => setActiveIndex(i => (i + 1) % SLIDES.length),
      INTERVAL_MS
    );
  }, []);

  const stop = useCallback(() => {
    clearInterval(intervalRef.current);
    intervalRef.current = null;
  }, []);

  useEffect(() => {
    start();
    return stop;
  }, [start, stop]);

  const goTo = useCallback((index) => {
    setActiveIndex(index);
    start(); // resets the 5-second countdown
  }, [start]);

  const prev = useCallback(() => {
    setActiveIndex(i => (i - 1 + SLIDES.length) % SLIDES.length);
    start();
  }, [start]);

  const next = useCallback(() => {
    setActiveIndex(i => (i + 1) % SLIDES.length);
    start();
  }, [start]);

  return (
    <div
      className={styles.hero}
      onMouseEnter={stop}
      onMouseLeave={start}
    >
      <button
        className={`${styles.heroArrow} ${styles.heroArrowLeft}`}
        onClick={prev}
        aria-label="Предыдущий слайд"
        type="button"
      >
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <path d="M11 4L6 9l5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      <div className={styles.heroInner}>
        <div className={styles.heroSlider}>
          {SLIDES.map((slide, i) => (
            <div
              key={i}
              className={`${styles.heroSlide} ${i === activeIndex ? styles.slideActive : ''}`}
              aria-hidden={i !== activeIndex}
            >
              <div className={styles.heroLabel}>{slide.label}</div>
              <h1 className={styles.heroTitle}>
                {slide.title}<br />
                <span className={styles.heroTitleHighlight}>{slide.highlight}</span>
              </h1>
              <p className={styles.heroSub}>{slide.sub}</p>
            </div>
          ))}
        </div>

      </div>

      <button
        className={`${styles.heroArrow} ${styles.heroArrowRight}`}
        onClick={next}
        aria-label="Следующий слайд"
        type="button"
      >
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <path d="M7 4l5 5-5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      <div className={styles.heroDots}>
        {SLIDES.map((_, i) => (
          <span
            key={i}
            className={`${styles.heroDot} ${i === activeIndex ? styles.active : ''}`}
            onClick={() => goTo(i)}
            role="button"
            aria-label={`Слайд ${i + 1}`}
          />
        ))}
      </div>
    </div>
  );
}
