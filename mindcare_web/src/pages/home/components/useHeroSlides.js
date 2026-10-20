import { useState, useEffect } from 'react';
import { getBannerSlides } from '../../../api/bannerSlides.api';

export function useHeroSlides(placement = 'home') {
  const [slides, setSlides] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getBannerSlides(placement)
      .then(data => { if (!cancelled) setSlides(Array.isArray(data) ? data : []); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [placement]);

  return { slides, loading };
}
