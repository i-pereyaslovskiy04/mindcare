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
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

export default function Hero() {
  const [activeIndex, setActiveIndex] = useState(0);
  const intervalRef = useRef(null);
  // Пауза по наведению и по фокусу — считаются раздельно: увод фокуса не должен
  // снимать паузу, пока курсор всё ещё над баннером, и наоборот.
  // В ref, а не в state: start() должен видеть актуальное значение,
  // не перезапускаясь при каждой смене hover.
  const hoverRef = useRef(false);
  const focusRef = useRef(false);

  const [reducedMotion, setReducedMotion] = useState(
    () => window.matchMedia?.(REDUCED_MOTION_QUERY).matches ?? false
  );

  useEffect(() => {
    const mq = window.matchMedia?.(REDUCED_MOTION_QUERY);
    if (!mq) return;
    const onChange = (e) => setReducedMotion(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  // Always clears the previous interval before starting a new one — no drift possible.
  // Пока слайдер на паузе (или включён reduced motion) таймер не заводится:
  // клик по стрелке/точке при наведённом курсоре не должен возобновлять автопрокрутку.
  const start = useCallback(() => {
    clearInterval(intervalRef.current);
    intervalRef.current = null;
    if (hoverRef.current || focusRef.current || reducedMotion) return;
    intervalRef.current = setInterval(
      () => setActiveIndex(i => (i + 1) % SLIDES.length),
      INTERVAL_MS
    );
  }, [reducedMotion]);

  const stop = useCallback(() => {
    clearInterval(intervalRef.current);
    intervalRef.current = null;
  }, []);

  useEffect(() => {
    start();
    return stop;
  }, [start, stop]);

  const handleMouseEnter = useCallback(() => {
    hoverRef.current = true;
    stop();
  }, [stop]);

  const handleMouseLeave = useCallback(() => {
    hoverRef.current = false;
    start();
  }, [start]);

  // React реализует onFocus/onBlur через focusin/focusout, поэтому они
  // всплывают со стрелок и точек внутри баннера.
  const handleFocus = useCallback(() => {
    focusRef.current = true;
    stop();
  }, [stop]);

  const handleBlur = useCallback(() => {
    focusRef.current = false;
    start();
  }, [start]);

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
      data-hero-banner
      role="region"
      aria-roledescription="карусель"
      aria-label="Баннер главной страницы"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleFocus}
      onBlur={handleBlur}
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
          <button
            key={i}
            type="button"
            className={`${styles.heroDot} ${i === activeIndex ? styles.active : ''}`}
            onClick={() => goTo(i)}
            aria-label={`Слайд ${i + 1}`}
            aria-current={i === activeIndex ? 'true' : undefined}
          />
        ))}
      </div>
    </div>
  );
}
