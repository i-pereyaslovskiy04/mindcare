import { useState, useEffect, useRef, useCallback } from 'react';
import styles from './Hero.module.css';
import { useHeroSlides } from './useHeroSlides';

// Fallback по каждой странице — показывается, пока не загружены слайды с API
// или пока в БД нет ни одного активного слайда этой страницы (например,
// сразу после деплоя). Для 'home' — тот же текст, что раньше был захардкожен;
// для 'services' — прежний статичный PageHero этой страницы.
const DEFAULT_SLIDES_BY_PLACEMENT = {
  home: [
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
  ],
  services: [
    {
      label: 'Донецкий государственный университет',
      title: 'Центр психологической помощи ДонГУ',
      sub: 'Поддержка, развитие и психологическое благополучие студентов и сотрудников университета. Мы помогаем справляться с трудностями и находить внутренние ресурсы.',
    },
  ],
  about: [
    {
      label: 'Донецкий государственный университет',
      title: 'Ресурсный центр',
      highlight: 'практической психологии',
      sub: 'Психологическая помощь и поддержка студентов, преподавателей и сотрудников ДонГУ',
    },
  ],
  materials: [
    {
      label: 'Ресурсный центр практической психологии',
      title: 'Материалы',
      sub: 'Статьи, вебинары и упражнения для поддержки психологического здоровья',
    },
  ],
};

const ARIA_LABEL_BY_PLACEMENT = {
  home: 'Баннер главной страницы',
  services: 'Баннер страницы услуг',
  about: 'Баннер страницы «О центре»',
  materials: 'Баннер страницы материалов',
};

const INTERVAL_MS = 5000;
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

export default function Hero({ placement = 'home' }) {
  const { slides: fetchedSlides, loading: slidesLoading } = useHeroSlides(placement);
  const defaultSlides = DEFAULT_SLIDES_BY_PLACEMENT[placement] || DEFAULT_SLIDES_BY_PLACEMENT.home;
  const slides = (!slidesLoading && fetchedSlides.length > 0) ? fetchedSlides : defaultSlides;
  const ariaLabel = ARIA_LABEL_BY_PLACEMENT[placement] || ARIA_LABEL_BY_PLACEMENT.home;

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
    if (hoverRef.current || focusRef.current || reducedMotion || slides.length <= 1) return;
    intervalRef.current = setInterval(
      () => setActiveIndex(i => (i + 1) % slides.length),
      INTERVAL_MS
    );
  }, [reducedMotion, slides.length]);

  const stop = useCallback(() => {
    clearInterval(intervalRef.current);
    intervalRef.current = null;
  }, []);

  useEffect(() => {
    start();
    return stop;
  }, [start, stop]);

  // Сброс индекса при смене массива слайдов (fallback → загруженные с API),
  // чтобы activeIndex не указывал за пределы нового массива.
  useEffect(() => {
    setActiveIndex(0);
  }, [slides]);

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
    setActiveIndex(i => (i - 1 + slides.length) % slides.length);
    start();
  }, [start, slides.length]);

  const next = useCallback(() => {
    setActiveIndex(i => (i + 1) % slides.length);
    start();
  }, [start, slides.length]);

  return (
    <div
      className={styles.hero}
      data-hero-banner
      role="region"
      aria-roledescription="карусель"
      aria-label={ariaLabel}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleFocus}
      onBlur={handleBlur}
    >
      {slides.map((slide, i) => slide.image_url && (
        <div
          key={`bg-${i}`}
          className={`${styles.heroSlideBg} ${i === activeIndex ? styles.slideActive : ''}`}
          style={{ '--slide-image': `url("${slide.image_url}")` }}
          aria-hidden="true"
          data-hero-slide-bg
          data-testid={`hero-slide-bg-${i}`}
        />
      ))}

      {slides.length > 1 && (
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
      )}

      <div className={styles.heroInner}>
        <div className={styles.heroSlider}>
          {slides.map((slide, i) => (
            <div
              key={i}
              className={[
                styles.heroSlide,
                i === activeIndex ? styles.slideActive : '',
                // Подложка под текст — только когда у слайда есть фоновая
                // картинка (иначе текущий вид без картинки не должен меняться).
                slide.image_url ? styles.hasImage : '',
              ].filter(Boolean).join(' ')}
              aria-hidden={i !== activeIndex}
              data-testid={`hero-slide-${i}`}
            >
              {slide.label && <div className={styles.heroLabel}>{slide.label}</div>}
              <h1 className={styles.heroTitle}>
                {slide.title}
                {slide.highlight && (
                  <>
                    <br />
                    <span className={styles.heroTitleHighlight}>{slide.highlight}</span>
                  </>
                )}
              </h1>
              {slide.sub && <p className={styles.heroSub}>{slide.sub}</p>}
              {slide.link_url && (
                <a
                  className={styles.heroCta}
                  href={slide.link_url}
                  // Неактивный слайд скрыт (opacity/pointer-events), но без
                  // tabIndex=-1 его ссылка всё равно оставалась бы в Tab-обходе.
                  tabIndex={i === activeIndex ? undefined : -1}
                >
                  Подробнее
                </a>
              )}
            </div>
          ))}
        </div>

      </div>

      {slides.length > 1 && (
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
      )}

      {slides.length > 1 && (
        <div className={styles.heroDots}>
          {slides.map((_, i) => (
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
      )}
    </div>
  );
}
