import { useState, useEffect } from 'react';
import { getUser, createUser, updateUser } from '../../../../api/users.api';
import { formatPhoneInput } from '../phone';
import { isStaffRole } from '../roleLabels';
import { VALID_BASIS_TYPES } from '../legalBasis';

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
const EDIT_INITIAL = {
  full_name: '',
  phone: '',
  role: '',
  is_active: true,
  // Документированное основание для смены роли на staff/admin (НЕ «согласие»).
  legal_basis_confirmed: false,
  basis_type: 'service_duty',
  basis_reference: '',
  legal_basis_comment: '',
};
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const VALID_ROLES = ['psychologist', 'admin', 'supervisor'];

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

/**
 * Legal basis нужен ТОЛЬКО когда роль реально изменилась и новая роль —
 * staff/admin (psychologist/supervisor/admin). staff → student, student без
 * смены и unchanged роль основания не требуют (совпадает с backend Stage 31f-fix).
 */
function roleChangeNeedsBasis(values, initialRole) {
  return values.role !== initialRole && isStaffRole(values.role);
}

function validateEdit(values, initialRole) {
  const errs = {};
  if (!values.full_name || values.full_name.trim().length < 2)
    errs.full_name = 'Минимум 2 символа';

  if (roleChangeNeedsBasis(values, initialRole)) {
    if (!values.legal_basis_confirmed)
      errs.legal_basis_confirmed =
        'Подтвердите наличие документированного основания';
    if (!VALID_BASIS_TYPES.includes(values.basis_type))
      errs.basis_type = 'Выберите тип основания';
    if (!values.basis_reference || !values.basis_reference.trim())
      errs.basis_reference = 'Укажите документ-основание';
  }
  return errs;
}

/**
 * Минимальный PATCH-payload для edit:
 *   - всегда: full_name, phone, is_active;
 *   - role — только если реально изменилась (иначе не отправляем);
 *   - legal basis fields — только при смене роли на staff/admin.
 * Невалидный legal basis сюда не доходит — отсекается validateEdit до submit.
 */
function buildEditPayload(values, initialRole) {
  const payload = {
    full_name: values.full_name,
    phone:     values.phone,
    is_active: values.is_active,
  };
  if (values.role !== initialRole) {
    payload.role = values.role;
    if (isStaffRole(values.role)) {
      payload.legal_basis_confirmed = values.legal_basis_confirmed;
      payload.basis_type           = values.basis_type;
      payload.basis_reference      = values.basis_reference?.trim() || null;
      payload.legal_basis_comment  = values.legal_basis_comment?.trim() || null;
    }
  }
  return payload;
}

export function useUserForm({ mode, uuid, onSuccess }) {
  const isCreate = mode === 'create';

  const [values, setValues] = useState(isCreate ? CREATE_INITIAL : EDIT_INITIAL);
  // Исходная роль пользователя — чтобы понять, изменилась ли роль (legal basis
  // нужен только при реальной смене на staff/admin). null до загрузки.
  const [initialRole, setInitialRole] = useState(null);
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
        setInitialRole(user.role);
        setValues({
          ...EDIT_INITIAL,
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
    let nextValue;
    if (type === 'checkbox') nextValue = checked;
    else if (name === 'phone') nextValue = formatPhoneInput(value);
    else nextValue = value;
    setValues((prev) => ({ ...prev, [name]: nextValue }));
    setErrors((prev) => ({ ...prev, [name]: undefined }));
  }

  function handleSubmit(e) {
    e.preventDefault();

    const errs = isCreate ? validateCreate(values) : validateEdit(values, initialRole);
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }

    setSubmitting(true);
    const payload = isCreate
      ? {
          // Пустые опциональные поля основания отправляем как null, не ''
          ...values,
          basis_reference: values.basis_reference?.trim() || null,
          legal_basis_comment: values.legal_basis_comment?.trim() || null,
        }
      : buildEditPayload(values, initialRole);
    const request = isCreate ? createUser(payload) : updateUser(uuid, payload);

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
    : { values, errors, loading, submitting, handleChange, handleSubmit, initialRole };
}
