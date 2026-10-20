import { useCallback, useEffect, useRef, useState } from 'react';
import { getPsychologistStudent } from '../../../api/psychologist.api';

export function useStudentCard(studentId) {
  const [student, setStudent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const requestId = useRef(0);

  const fetchCard = useCallback(async (id) => {
    if (!id) return;
    const rid = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const data = await getPsychologistStudent(id);
      if (rid !== requestId.current) return;
      setStudent(data);
    } catch (err) {
      if (rid !== requestId.current) return;
      setError(err.message ?? 'Ошибка загрузки');
    } finally {
      if (rid === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCard(studentId);
  }, [studentId, fetchCard]);

  const refetch = () => fetchCard(studentId);

  return { student, loading, error, refetch };
}
