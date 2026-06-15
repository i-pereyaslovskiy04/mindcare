/**
 * Документированное основание обработки ПДн (legal basis) для staff/admin.
 *
 * НЕ «согласие за пользователя»: организация фиксирует документированное
 * основание для создания учётной записи / назначения роли и обработки ПДн.
 * basis_type values должны совпадать с backend-политикой (Stage 23b / 31f-fix),
 * чтобы create и edit flow не расходились с сервером.
 */

export const BASIS_TYPE_OPTIONS = [
  { value: 'service_duty',         label: 'Служебная необходимость' },
  { value: 'employment',           label: 'Трудовое основание' },
  { value: 'contract',             label: 'Договор' },
  { value: 'administrative_order', label: 'Административный приказ' },
  { value: 'other',                label: 'Иное' },
];

export const VALID_BASIS_TYPES = BASIS_TYPE_OPTIONS.map((o) => o.value);

/** Подтверждение при СОЗДАНИИ пользователя. */
export const CREATE_LEGAL_BASIS_LABEL =
  'Подтверждаю наличие документированного основания для создания ' +
  'учётной записи и обработки персональных данных пользователя.';

/** Подтверждение при СМЕНЕ роли на staff/admin в edit-форме. */
export const ROLE_CHANGE_LEGAL_BASIS_LABEL =
  'Подтверждаю наличие документированного основания для назначения ' +
  'этой роли и обработки персональных данных.';
