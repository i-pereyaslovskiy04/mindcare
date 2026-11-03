import { useEffect, useState } from 'react';
import { getPsychologistStudents } from '../../../api/psychologist.api';

/**
 * Число клиентов психолога — total списка «Мои студенты» (строго активное
 * сопровождение). null — неизвестно (загрузка или ошибка): не подменяется нулём.
 */
export default function useClientsTotal() {
  const [total, setTotal] = useState(null);

  useEffect(() => {
    let alive = true;
    getPsychologistStudents({ page: 1, size: 1 })
      .then((data) => {
        const value = Number(data?.total);
        if (alive && Number.isInteger(value) && value >= 0) setTotal(value);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  return total;
}
