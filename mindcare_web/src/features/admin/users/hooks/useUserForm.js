import { useState, useEffect } from 'react';
import { getUser, createUser, updateUser } from '../../../../api/users.api';
import { formatPhoneInput } from '../phone';
import { isStaffRole } from '../roleLabels';
import { VALID_BASIS_TYPES } from '../legalBasis';
import { normalizeRoles } from '../../../../shared/lib/roles';

const CREATE_INITIAL = {
  full_name: '',
  email: '',
  roles: ['psychologist'], // multi-role staff set (ADR-018)
  // Документированное основание (legal basis) — НЕ «согласие за пользователя»
  legal_basis_confirmed: false,
  basis_type: 'service_duty',
  basis_reference: '',
  legal_basis_comment: '',
};
const EDIT_INITIAL = {
  full_name: '',
  phone: '',
  roles: [], // целевой набор STAFF-ролей (student сохраняется backend'ом)
  is_active: true,
  // Документированное основание при добавлении staff-роли (НЕ «согласие»).
  legal_basis_confirmed: false,
  basis_type: 'service_duty',
  basis_reference: '',
  legal_basis_comment: '',
};
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function sameSet(a, b) {
  if (a.length !== b.length) return false;
  const sb = new Set(b);
  return a.every((x) => sb.has(x));
}

/** Роли, которые добавляются относительно исходного staff-набора. */
function rolesToAdd(roles, initialStaffRoles) {
  return roles.filter((r) => !initialStaffRoles.includes(r));
}

function validateCreate(values) {
  const errs = {};
  if (!values.full_name || values.full_name.trim().length < 2)
    errs.full_name = 'Минимум 2 символа';
  if (!values.email || !EMAIL_RE.test(values.email))
    errs.email = 'Введите корректный email';
  if (!values.roles || values.roles.length === 0)
    errs.roles = 'Выберите хотя бы одну роль';
  else if (values.roles.some((r) => !isStaffRole(r)))
    errs.roles = 'Через админку назначаются только служебные роли';
  if (!VALID_BASIS_TYPES.includes(values.basis_type))
    errs.basis_type = 'Выберите тип основания';
  // basis_reference обязателен (синхронизация с backend: непустой после trim).
  if (!values.basis_reference || !values.basis_reference.trim())
    errs.basis_reference = 'Укажите документ-основание';
  if (!values.legal_basis_confirmed)
    errs.legal_basis_confirmed =
      'Подтвердите наличие документированного основания';
  return errs;
}

/**
 * Backend разрешает ДОБАВЛЕНИЕ staff-роли только пользователю, у которого уже
 * есть активная staff-роль (`_apply_role_and_scalar_changes`: `added and not
 * current_staff` → 422). Student-only и roleless пользователи не могут
 * получить первую staff-роль через edit — только через POST /admin/users.
 */
function canManageStaffRoles(initialStaffRoles) {
  return initialStaffRoles.length > 0;
}

function validateEdit(values, initialStaffRoles, hasStudent) {
  const errs = {};
  if (!values.full_name || values.full_name.trim().length < 2)
    errs.full_name = 'Минимум 2 символа';

  // Roles не менялись — unchanged empty staff-набор (roleless/student-only
  // пользователь) НЕ должен блокировать чисто скалярное редактирование.
  if (sameSet(values.roles, initialStaffRoles)) return errs;

  const added = rolesToAdd(values.roles, initialStaffRoles);

  if (added.length > 0 && !canManageStaffRoles(initialStaffRoles)) {
    errs.roles =
      'Назначение служебной роли доступно только пользователю, у которого ' +
      'уже есть служебная роль. Новых сотрудников создавайте через ' +
      '«Создать пользователя»';
    return errs;
  }

  // Нельзя оставить пользователя без активных ролей: пустой staff-набор
  // допустим только если у пользователя есть (сохраняемая) роль student.
  if (values.roles.length === 0 && !hasStudent)
    errs.roles = 'У пользователя должна остаться хотя бы одна роль';
  if (values.roles.some((r) => !isStaffRole(r)))
    errs.roles = 'Через админку назначаются только служебные роли';

  // Legal basis нужен только при добавлении новой staff-роли.
  if (added.length > 0) {
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

function buildCreatePayload(values) {
  return {
    full_name: values.full_name,
    email: values.email,
    roles: values.roles,
    legal_basis_confirmed: values.legal_basis_confirmed,
    basis_type: values.basis_type,
    basis_reference: values.basis_reference?.trim() || null,
    legal_basis_comment: values.legal_basis_comment?.trim() || null,
  };
}

/**
 * Минимальный PATCH-payload для edit:
 *   - всегда: full_name, phone, is_active;
 *   - roles (target staff set) — только если набор реально изменился;
 *   - legal basis fields — только при добавлении новой staff-роли.
 * `student` не отправляется — backend сохраняет его сам.
 */
function buildEditPayload(values, initialStaffRoles) {
  const payload = {
    full_name: values.full_name,
    phone:     values.phone,
    is_active: values.is_active,
  };
  if (!sameSet(values.roles, initialStaffRoles)) {
    payload.roles = values.roles;
    if (rolesToAdd(values.roles, initialStaffRoles).length > 0) {
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
  // Исходный STAFF-набор и наличие student — чтобы понять, какие роли реально
  // добавляются (legal basis нужен только на добавление). null до загрузки.
  const [initialStaffRoles, setInitialStaffRoles] = useState([]);
  const [hasStudent, setHasStudent] = useState(false);
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
        const roles = normalizeRoles(user);
        const staff = roles.filter(isStaffRole);
        setInitialStaffRoles(staff);
        setHasStudent(roles.includes('student'));
        setValues({
          ...EDIT_INITIAL,
          full_name: user.full_name,
          phone:     user.phone || '',
          roles:     staff,
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

  /** Тоггл staff-роли в checkbox-контроле. */
  function toggleRole(role) {
    if (!isStaffRole(role)) return; // student через админку не управляется
    // Roleless/student-only: backend отклоняет добавление первой staff-роли
    // через edit (422) — контрол должен быть недоступен ещё на фронте.
    if (!isCreate && !canManageStaffRoles(initialStaffRoles)) return;
    setValues((prev) => {
      const has = prev.roles.includes(role);
      const roles = has
        ? prev.roles.filter((r) => r !== role)
        : [...prev.roles, role];
      return { ...prev, roles };
    });
    setErrors((prev) => ({ ...prev, roles: undefined }));
  }

  function handleSubmit(e) {
    e.preventDefault();

    const errs = isCreate
      ? validateCreate(values)
      : validateEdit(values, initialStaffRoles, hasStudent);
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }

    setSubmitting(true);
    const payload = isCreate
      ? buildCreatePayload(values)
      : buildEditPayload(values, initialStaffRoles);
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

  const editNeedsBasis =
    !isCreate && rolesToAdd(values.roles, initialStaffRoles).length > 0;

  return isCreate
    ? {
        values, errors, loading: false, submitting,
        handleChange, handleSubmit, toggleRole, reset,
      }
    : {
        values, errors, loading, submitting,
        handleChange, handleSubmit, toggleRole,
        initialStaffRoles, hasStudent, editNeedsBasis,
        canManageStaffRoles: canManageStaffRoles(initialStaffRoles),
      };
}
