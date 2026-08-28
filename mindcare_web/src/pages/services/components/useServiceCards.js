import { useState, useEffect } from 'react';
import { getServiceCards } from '../../../api/serviceCards.api';

export function useServiceCards() {
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getServiceCards()
      .then(data => { if (!cancelled) setCards(Array.isArray(data) ? data : []); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { cards, loading };
}
