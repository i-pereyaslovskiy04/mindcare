/**
 * Presentation-карты admin audit viewer (Stage 8 UI).
 *
 * Здесь и только здесь машинные коды журналов превращаются в человекочитаемые
 * подписи. Правила:
 *
 *   - карты ЗАКРЫТЫЕ: неизвестный код никогда не показывается «как есть» и не
 *     достраивается из raw-значения (никакого replaceAll('_', ' ')) — иначе
 *     будущее backend-событие утекло бы в UI без ревью подписи;
 *   - backend уже подменяет неизвестное событие на LEGACY_EVENT_CODE, но
 *     fallback здесь всё равно нужен: карты могут отстать от registry;
 *   - подписи полей data_change_log вложены по таблице. В CHANGE_REGISTRY
 *     25 разрешённых ПАР таблица/поле и лишь 22 уникальных имени
 *     (description у group_sessions и meeting_types, full_name/phone у
 *     unregistered_student_cards и users), поэтому плоская карта подставляла бы
 *     чужую подпись.
 */

export const LEGACY_EVENT_CODE = 'legacy_unknown_event';
export const UNKNOWN_LABEL = 'Неизвестное или историческое событие';

// ── Категории событий (frontend-only группировка списка опций) ────────────────
// Управляют ТОЛЬКО составом опций: API принимает ровно один точный код события,
// фильтрации по категории не существует.

export const EVENT_CATEGORY_ORDER = [
  'users_roles',
  'auth_security',
  'consultations',
  'schedules',
  'notes',
  'chat',
  'testing',
  'content',
  'system',
  'audit_access',
];

export const EVENT_CATEGORY_LABELS = {
  users_roles:   'Пользователи и роли',
  auth_security: 'Вход и безопасность',
  consultations: 'Консультации',
  schedules:     'Расписания и групповые занятия',
  notes:         'Заметки сессий',
  chat:          'Чат и вложения',
  testing:       'Тестирование',
  content:       'Контент',
  system:        'Системные операции',
  audit_access:  'Просмотр аудита',
};

// ── audit_log: 87 событий ────────────────────────────────────────────────────

export const AUDIT_EVENT_LABELS = {
  // Пользователи и роли (20)
  admin_role_add:                          'Администратор добавил роль',
  admin_role_remove:                       'Администратор снял роль',
  admin_role_update:                       'Администратор изменил набор ролей',
  admin_user_activated:                    'Учётная запись разблокирована',
  admin_user_create_failed:                'Создание учётной записи отклонено',
  admin_user_created:                      'Учётная запись создана администратором',
  admin_user_deactivated:                  'Учётная запись заблокирована',
  admin_user_delete_failed:                'Удаление учётной записи отклонено',
  admin_user_deleted:                      'Учётная запись удалена',
  admin_user_update_failed:                'Изменение учётной записи отклонено',
  admin_user_updated:                      'Учётная запись изменена администратором',
  profile_updated:                         'Пользователь изменил свой профиль',
  profile_update_failed:                   'Изменение профиля отклонено',
  user_reactivated:                        'Учётная запись восстановлена',
  supervisor_create_student:               'Супервизор создал аккаунт студента',
  unregistered_student_card_archived:      'Карточка клиента без аккаунта архивирована',
  unregistered_student_card_create_failed: 'Создание карточки клиента отклонено',
  unregistered_student_card_created:       'Создана карточка клиента без аккаунта',
  unregistered_student_card_linked:        'Карточка клиента привязана к аккаунту',
  unregistered_student_card_updated:       'Карточка клиента без аккаунта изменена',

  // Консультации (16)
  appointment_cancel_failed:          'Отмена записи отклонена',
  appointment_cancelled:              'Запись на консультацию отменена',
  appointment_confirm_failed:         'Подтверждение записи отклонено',
  appointment_confirmed:              'Запись на консультацию подтверждена',
  appointment_create_failed:          'Создание записи отклонено',
  appointment_created:                'Создана запись на консультацию',
  appointment_decline_failed:         'Отклонение записи не выполнено',
  appointment_declined:               'Запись на консультацию отклонена',
  meeting_type_activated:             'Тип встречи включён',
  meeting_type_created:               'Создан тип встречи',
  meeting_type_deactivated:           'Тип встречи отключён',
  meeting_type_updated:               'Тип встречи изменён',
  supervisor_assign_psychologist:     'Супервизор назначил психолога',
  supervisor_close_engagement:        'Супервизор закрыл сопровождение',
  supervisor_reactivate_psychologist: 'Супервизор возобновил сопровождение',
  supervisor_transfer_psychologist:   'Супервизор передал клиента другому психологу',

  // Расписания и групповые занятия (19)
  group_session_booking_closed:         'Запись на групповое занятие закрыта',
  group_session_booking_opened:         'Запись на групповое занятие открыта',
  group_session_cancelled:              'Групповое занятие отменено',
  group_session_completed:              'Групповое занятие завершено',
  group_session_created:                'Создано групповое занятие',
  group_session_registered:             'Студент записался на групповое занятие',
  group_session_registration_cancelled: 'Запись на групповое занятие отменена',
  group_session_updated:                'Групповое занятие изменено',
  schedule_auto_extended:               'Расписание продлено автоматически',
  schedule_break_created:               'Добавлен перерыв в расписании',
  schedule_break_deactivated:           'Перерыв в расписании отключён',
  schedule_created:                     'Создана серия расписания',
  schedule_deactivated:                 'Серия расписания отключена',
  schedule_exception_created:           'Добавлено исключение в расписании',
  schedule_extended:                    'Расписание продлено',
  schedule_restored:                    'Серия расписания восстановлена',
  schedule_rule_created:                'Добавлено рабочее окно',
  schedule_rule_deactivated:            'Рабочее окно отключено',
  schedule_updated:                     'Серия расписания изменена',

  // Заметки сессий (3)
  session_note_content_read: 'Прочитано содержимое заметки сессии',
  session_note_created:      'Создана заметка сессии',
  session_note_updated:      'Заметка сессии изменена',

  // Чат и вложения (6)
  chat_attachment_downloaded:  'Скачано вложение чата',
  chat_attachment_uploaded:    'Загружено вложение чата',
  chat_conversation_created:   'Создана беседа',
  chat_message_deleted:        'Сообщение чата удалено',
  chat_message_edited:         'Сообщение чата изменено',
  system_conversation_created: 'Создана системная беседа',

  // Тестирование (6)
  test_consent_accepted: 'Принято согласие перед тестированием',
  test_created:          'Создана методика',
  test_deleted:          'Методика удалена',
  test_duplicated:       'Методика скопирована',
  test_submitted:        'Тест пройден',
  test_updated:          'Методика изменена',

  // Контент (12)
  article_created:  'Создан материал',
  article_deleted:  'Материал удалён',
  article_updated:  'Материал изменён',
  category_created: 'Создан тип материалов',
  category_deleted: 'Тип материалов удалён',
  category_updated: 'Тип материалов изменён',
  news_created:     'Создана новость',
  news_deleted:     'Новость удалена',
  news_updated:     'Новость изменена',
  tag_created:      'Создана тема',
  tag_deleted:      'Тема удалена',
  tag_updated:      'Тема изменена',

  // Системные операции (4)
  email_domain_add:        'Добавлен домен регистрации',
  email_domain_disable:    'Домен регистрации отключён',
  email_domain_reactivate: 'Домен регистрации включён снова',
  email_domain_update:     'Домен регистрации изменён',

  // Просмотр аудита (1)
  audit_logs_viewed: 'Просмотр журнала аудита',
};

// ── auth_log: 7 событий ──────────────────────────────────────────────────────

export const AUTH_EVENT_LABELS = {
  failed_login:           'Неудачная попытка входа',
  login:                  'Вход в систему',
  logout:                 'Выход из системы',
  password_change:        'Смена пароля',
  password_reset:         'Восстановление пароля',
  registration_failed:    'Регистрация не завершена',
  registration_succeeded: 'Регистрация завершена',
};

export const EVENT_CATEGORIES = {
  // audit_log
  admin_role_add: 'users_roles',
  admin_role_remove: 'users_roles',
  admin_role_update: 'users_roles',
  admin_user_activated: 'users_roles',
  admin_user_create_failed: 'users_roles',
  admin_user_created: 'users_roles',
  admin_user_deactivated: 'users_roles',
  admin_user_delete_failed: 'users_roles',
  admin_user_deleted: 'users_roles',
  admin_user_update_failed: 'users_roles',
  admin_user_updated: 'users_roles',
  profile_updated: 'users_roles',
  profile_update_failed: 'users_roles',
  user_reactivated: 'users_roles',
  supervisor_create_student: 'users_roles',
  unregistered_student_card_archived: 'users_roles',
  unregistered_student_card_create_failed: 'users_roles',
  unregistered_student_card_created: 'users_roles',
  unregistered_student_card_linked: 'users_roles',
  unregistered_student_card_updated: 'users_roles',

  appointment_cancel_failed: 'consultations',
  appointment_cancelled: 'consultations',
  appointment_confirm_failed: 'consultations',
  appointment_confirmed: 'consultations',
  appointment_create_failed: 'consultations',
  appointment_created: 'consultations',
  appointment_decline_failed: 'consultations',
  appointment_declined: 'consultations',
  meeting_type_activated: 'consultations',
  meeting_type_created: 'consultations',
  meeting_type_deactivated: 'consultations',
  meeting_type_updated: 'consultations',
  supervisor_assign_psychologist: 'consultations',
  supervisor_close_engagement: 'consultations',
  supervisor_reactivate_psychologist: 'consultations',
  supervisor_transfer_psychologist: 'consultations',

  group_session_booking_closed: 'schedules',
  group_session_booking_opened: 'schedules',
  group_session_cancelled: 'schedules',
  group_session_completed: 'schedules',
  group_session_created: 'schedules',
  group_session_registered: 'schedules',
  group_session_registration_cancelled: 'schedules',
  group_session_updated: 'schedules',
  schedule_auto_extended: 'schedules',
  schedule_break_created: 'schedules',
  schedule_break_deactivated: 'schedules',
  schedule_created: 'schedules',
  schedule_deactivated: 'schedules',
  schedule_exception_created: 'schedules',
  schedule_extended: 'schedules',
  schedule_restored: 'schedules',
  schedule_rule_created: 'schedules',
  schedule_rule_deactivated: 'schedules',
  schedule_updated: 'schedules',

  session_note_content_read: 'notes',
  session_note_created: 'notes',
  session_note_updated: 'notes',

  chat_attachment_downloaded: 'chat',
  chat_attachment_uploaded: 'chat',
  chat_conversation_created: 'chat',
  chat_message_deleted: 'chat',
  chat_message_edited: 'chat',
  system_conversation_created: 'chat',

  test_consent_accepted: 'testing',
  test_created: 'testing',
  test_deleted: 'testing',
  test_duplicated: 'testing',
  test_submitted: 'testing',
  test_updated: 'testing',

  article_created: 'content',
  article_deleted: 'content',
  article_updated: 'content',
  category_created: 'content',
  category_deleted: 'content',
  category_updated: 'content',
  news_created: 'content',
  news_deleted: 'content',
  news_updated: 'content',
  tag_created: 'content',
  tag_deleted: 'content',
  tag_updated: 'content',

  email_domain_add: 'system',
  email_domain_disable: 'system',
  email_domain_reactivate: 'system',
  email_domain_update: 'system',

  audit_logs_viewed: 'audit_access',

  // auth_log — у него своя вкладка с плоским списком из семи пунктов. Категория
  // объявлена, чтобы карта покрывала все 94 кода registry.
  failed_login: 'auth_security',
  login: 'auth_security',
  logout: 'auth_security',
  password_change: 'auth_security',
  password_reset: 'auth_security',
  registration_failed: 'auth_security',
  registration_succeeded: 'auth_security',
};

// ── Коды отказа (17) ─────────────────────────────────────────────────────────

export const FAILURE_CODE_LABELS = {
  access_denied:         'Доступ запрещён',
  account_inactive:      'Учётная запись заблокирована',
  consent_required:      'Требуется согласие',
  domain_not_allowed:    'Домен почты не разрешён',
  email_already_exists:  'Email уже используется',
  engagement_required:   'Нужно активное сопровождение',
  internal_error:        'Внутренняя ошибка',
  invalid_credentials:   'Неверные учётные данные',
  invalid_request:       'Некорректный запрос',
  legal_basis_required:  'Требуется документированное основание',
  no_active_roles:       'Нет активных ролей',
  otp_expired:           'Код подтверждения истёк',
  otp_invalid:           'Неверный код подтверждения',
  password_policy:       'Пароль не отвечает требованиям',
  role_policy_violation: 'Нарушение политики ролей',
  self_admin_protected:  'Нельзя снять роль администратора у себя',
  user_not_found:        'Пользователь не найден',
};

// ── Типы объектов (23) ───────────────────────────────────────────────────────

export const ENTITY_TYPE_LABELS = {
  allowed_email_domain:       'Домен регистрации',
  appointment:                'Запись на консультацию',
  article:                    'Материал',
  category:                   'Тип материалов',
  chat_attachment:            'Вложение чата',
  chat_conversation:          'Беседа',
  chat_message:               'Сообщение чата',
  consent_record:             'Запись о согласии',
  group_session:              'Групповое занятие',
  group_session_registration: 'Запись на групповое занятие',
  meeting_type:               'Тип встречи',
  news:                       'Новость',
  schedule_break:             'Перерыв в расписании',
  schedule_exception:         'Исключение в расписании',
  schedule_rule:              'Рабочее окно',
  schedule_series:            'Серия расписания',
  session_note:               'Заметка сессии',
  tag:                        'Тема',
  test:                       'Методика',
  test_result:                'Результат теста',
  therapy_engagement:         'Сопровождение',
  unregistered_student_card:  'Карточка клиента без аккаунта',
  user:                       'Пользователь',
};

/** Тип цели, для которого backend запрещает точный числовой идентификатор. */
export const USER_ENTITY_TYPE = 'user';

// ── data_change_log ──────────────────────────────────────────────────────────

export const TABLE_LABELS = {
  group_sessions:             'Групповые занятия',
  meeting_types:              'Типы встреч',
  unregistered_student_cards: 'Карточки клиентов без аккаунта',
  users:                      'Пользователи',
};

/** Таблица, для которой backend запрещает точный record_id. */
export const USER_TABLE_NAME = 'users';

export const OPERATION_LABELS = {
  INSERT: 'Добавление',
  UPDATE: 'Изменение',
  DELETE: 'Удаление',
};

/**
 * Подписи allowlisted полей — по таблице-владельцу. 25 пар, 22 уникальных имени.
 * Значения полей backend по умолчанию не отдаёт вовсе — здесь только имена.
 */
export const CHANGED_FIELD_LABELS = {
  group_sessions: {
    capacity:        'Вместимость',
    description:     'Описание занятия',
    ends_at:         'Окончание',
    format:          'Формат',
    meeting_type_id: 'Тип встречи',
    psychologist_id: 'Психолог',
    starts_at:       'Начало',
    title:           'Название',
  },
  meeting_types: {
    allow_in_person:  'Очный формат',
    allow_online:     'Онлайн-формат',
    buffer_minutes:   'Буфер, мин',
    description:      'Описание типа встречи',
    display_order:    'Порядок отображения',
    duration_minutes: 'Длительность, мин',
    is_bookable:      'Доступен для записи',
    is_group:         'Групповой',
    name:             'Название',
  },
  unregistered_student_cards: {
    birth_date:      'Дата рождения',
    comment:         'Комментарий',
    email:           'Email',
    full_name:       'ФИО клиента',
    phone:           'Телефон клиента',
    primary_concern: 'Запрос клиента',
  },
  users: {
    full_name: 'ФИО',
    phone:     'Телефон',
  },
};

// ── Прочие подписи ───────────────────────────────────────────────────────────

export const ACTOR_KIND_LABELS = {
  user:        'Пользователь',
  system:      'Система',
  anonymous:   'Анонимный пользователь',
  unavailable: 'Удалённый или недоступный пользователь',
};

export const OUTCOME_LABELS = {
  success: 'Успешно',
  failure: 'Отказ',
};

export const OUTCOME_TONES = {
  success: 'success',
  failure: 'error',
};

export const JOURNAL_LABELS = {
  audit_log:       'Действия',
  auth_log:        'Входы и безопасность',
  data_change_log: 'Изменённые поля',
};

/** Имена применённых фильтров — приходят в details события audit_logs_viewed. */
export const FILTER_KEY_LABELS = {
  date_range:    'период',
  actor:         'участник',
  actor_kind:    'класс участника',
  actor_role:    'роль действия',
  event:         'событие',
  outcome:       'результат',
  entity:        'тип объекта',
  record:        'идентификатор записи',
  target:        'цель',
  success:       'результат входа',
  table:         'таблица',
  operation:     'операция',
  access_events: 'просмотры журнала',
};

/** Ключи details, которые разрешено показывать. Порядок — порядок вывода. */
export const DETAIL_KEY_ORDER = [
  'journal',
  'filter_keys',
  'roles_before',
  'roles_after',
  'added',
  'removed',
  'fields',
  'mime_type',
  'file_size',
  'linked_user_uuid',
];

export const DETAIL_KEY_LABELS = {
  journal:          'Журнал',
  filter_keys:      'Применённые фильтры',
  roles_before:     'Роли до',
  roles_after:      'Роли после',
  added:            'Добавлено',
  removed:          'Снято',
  fields:           'Изменённые поля',
  mime_type:        'Тип файла',
  file_size:        'Размер файла',
  linked_user_uuid: 'Привязанный пользователь',
};

/**
 * Подпись по закрытой карте. Неизвестный код НИКОГДА не показывается как есть:
 * подставляется нейтральный fallback.
 */
export function labelFor(map, code, fallback = UNKNOWN_LABEL) {
  if (typeof code !== 'string' || !code) return fallback;
  return Object.prototype.hasOwnProperty.call(map, code) ? map[code] : fallback;
}

/**
 * Подпись поля data_change_log с учётом таблицы-владельца. Для неизвестной пары
 * возвращается само имя поля: это стабильный машинный идентификатор из
 * allowlist'а backend'а, а не произвольный текст.
 */
export function changedFieldLabel(tableName, field) {
  const table = CHANGED_FIELD_LABELS[tableName];
  if (!table) return field;
  return Object.prototype.hasOwnProperty.call(table, field) ? table[field] : field;
}

/** Категория события; неизвестный код категории не получает. */
export function categoryOf(code) {
  return EVENT_CATEGORIES[code] ?? null;
}
