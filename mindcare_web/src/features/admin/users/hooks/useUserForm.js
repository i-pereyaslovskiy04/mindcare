import { useState, useEffect } from 'react';
import { getUser, createUser, updateUser } from '../../../../api/users.api';

const CREATE_INITIAL = {
  full_name: '',
  email: '',
  role: 'psychologist',
  // Документированное основание (legal basis) — НЕ «согласие за пользователя»
  legal_basis_confirmed: false,
  basis_type: 'service_duty',
  basis_reference: '',
  legal_basis_comment: '',
};
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const VALID_ROLES = ['psychologist', 'admin', 'supervisor'];
const VALID_BASIS_TYPES = [
  'service_duty', 'employment', 'contract', 'administrative_order', 'other',
];

function validateCreate(values) {
  const errs = {};
  if (!values.full_name || values.full_name.trim().length < 2)
    errs.full_name = 'Минимум 2 символа';
  if (!values.email || !EMAIL_RE.test(values.email))
    errs.email = 'Введите корректный email';
  if (!VALID_ROLES.includes(values.role))
    errs.role = 'Выберите роль';
  if (!VALID_BASIS_TYPES.includes(values.basis_type))
    errs.basis_type = 'Выберите тип основания';
  if (!values.legal_basis_confirmed)
    errs.legal_basis_confirmed =
      'Подтвердите наличие документированного основания';
  return errs;
}

function validateEdit(values) {
  const errs = {};
  if (!values.full_name || values.full_name.trim().length < 2)
    errs.full_name = 'Минимум 2 символа';
  if (!values.role)
    errs.role = 'Выберите роль';
  return errs;
}

export function useUserForm({ mode, uuid, onSuccess }) {
  const isCreate = mode === 'create';

  const [values, setValues] = useState(
    isCreate
      ? CREATE_INITIAL
      : { full_name: '', phone: '', role: '', is_active: true }
  );
  const [errors, setErrors]       = useState({});
  const [loading, setLoading]     = useState(!isCreate);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (isCreate || !uuid) return;

    let cancelled = false;
    setLoading(true);
    setErrors({});

    getUser(uuid)
      .then((user) => {
        if (cancelled) return;
        setValues({
          full_name: user.full_name,
          phone:     user.phone || '',
          role:      user.role,
          is_active: user.is_active,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setErrors({ _form: err.message });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [isCreate, uuid]);

  function handleChange(e) {
    const { name, value, type, checked } = e.target;
    setValues((prev) => ({ ...prev, [name]: type === 'checkbox' ? checked : value }));
    setErrors((prev) => ({ ...prev, [name]: undefined }));
  }

  function handleSubmit(e) {
    e.preventDefault();

    const errs = isCreate ? validateCreate(values) : validateEdit(values);
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }

    setSubmitting(true);
    // Пустые опциональные поля основания отправляем как null, не ''
    const payload = isCreate
      ? {
          ...values,
          basis_reference: values.basis_reference?.trim() || null,
          legal_basis_comment: values.legal_basis_comment?.trim() || null,
        }
      : values;
    const request = isCreate ? createUser(payload) : updateUser(uuid, values);

    request
      .then((result) => { onSuccess(result); })
      .catch((err)   => { setErrors({ _form: err.message }); })
      .finally(()    => { setSubmitting(false); });
  }

  function reset() {
    setValues(CREATE_INITIAL);
    setErrors({});
  }

  return isCreate
    ? { values, errors, loading: false, submitting, handleChange, handleSubmit, reset }
    : { values, errors, loading, submitting, handleChange, handleSubmit };
}
