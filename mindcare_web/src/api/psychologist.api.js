import { apiFetch } from './client';

export function getPsychologistStudents({ page = 1, size = 20, search } = {}) {
  const params = new URLSearchParams({ page, size });
  if (search) params.set('search', search);
  return apiFetch(`/api/psychologist/students?${params}`);
}

export function getPsychologistStudent(studentId) {
  return apiFetch(`/api/psychologist/students/${studentId}`);
}
