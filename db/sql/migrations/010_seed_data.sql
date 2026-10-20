-- ============================================
-- Migration 010: Seed Data
-- ============================================

-- Роли
INSERT INTO roles (name, display_name, description, is_system) VALUES
    ('student',      'Студент/Клиент',  'Проходит тесты, записывается на консультации', TRUE),
    ('psychologist', 'Психолог',        'Ведут консультации, управляет тестами',        TRUE),
    ('admin',        'Администратор',   'Полный доступ к системе',                     TRUE),
    ('supervisor',   'Супервизор',      'Наблюдает за работой психологов-стажёров',     TRUE);

-- Разрешения
INSERT INTO permissions (code, description, module) VALUES
    ('users.view_own',            'Просмотр своего профиля',              'users'),
    ('users.edit_own',            'Редактирование своего профиля',        'users'),
    ('users.view_all',            'Просмотр всех пользователей',          'users'),
    ('users.manage',              'Управление пользователями',            'users'),
    ('appointments.create',       'Создание записи на консультацию',      'appointments'),
    ('appointments.view_own',     'Просмотр своих консультаций',          'appointments'),
    ('appointments.view_assigned','Просмотр назначенных консультаций',    'appointments'),
    ('appointments.manage',       'Управление всеми консультациями',      'appointments'),
    ('tests.take',                'Прохождение тестов',                   'tests'),
    ('tests.view_own_results',    'Просмотр своих результатов',           'tests'),
    ('tests.view_client_results', 'Просмотр результатов клиентов',       'tests'),
    ('tests.manage',              'Управление тестами (CRUD)',            'tests'),
    ('content.view',              'Просмотр публичного контента',         'content'),
    ('content.manage',            'Управление контентом (статьи, новости)','content'),
    ('qa.ask',                    'Задать вопрос',                        'qa'),
    ('qa.answer',                 'Ответить на вопрос',                   'qa'),
    ('analytics.view',            'Просмотр аналитики',                   'analytics'),
    ('analytics.export',          'Экспорт данных',                       'analytics'),
    ('audit.view',                'Просмотр журнала аудита',              'audit');

-- Привязка разрешений к ролям

-- Студент
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'student' AND p.code IN (
    'users.view_own', 'users.edit_own',
    'appointments.create', 'appointments.view_own',
    'tests.take', 'tests.view_own_results',
    'content.view', 'qa.ask'
);

-- Психолог
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'psychologist' AND p.code IN (
    'users.view_own', 'users.edit_own',
    'appointments.view_assigned', 'appointments.manage',
    'tests.view_client_results', 'tests.manage',
    'content.view', 'content.manage',
    'qa.answer', 'analytics.view'
);

-- Администратор — все разрешения
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'admin';

-- Супервизор
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'supervisor' AND p.code IN (
    'users.view_own', 'users.edit_own', 'users.view_all',
    'appointments.view_assigned',
    'tests.view_client_results',
    'content.view', 'analytics.view', 'audit.view'
);

-- Категории
INSERT INTO categories (name, slug, description, display_order) VALUES
    ('Стресс и тревожность',  'stress',          'Методики диагностики стресса и тревоги',       1),
    ('Депрессия',             'depression',       'Диагностика депрессивных состояний',            2),
    ('ПТСР',                  'ptsd',             'Посттравматическое стрессовое расстройство',    3),
    ('Адаптация',             'adaptation',       'Адаптация первокурсников',                      4),
    ('Саморегуляция',         'self-regulation',  'Методы эмоциональной саморегуляции',            5),
    ('Конфликтология',        'conflicts',        'Разрешение конфликтов',                         6),
    ('Профориентация',        'career',           'Профессиональная ориентация и способности',     7),
    ('Общее самочувствие',    'wellbeing',        'Самопознание и общее самочувствие',             8),
    ('Первая помощь',         'first-aid',        'Первая психологическая помощь',                 9),
    ('Кризисные ситуации',    'crisis',           'Кризисные и экстренные ситуации',              10);

-- Шаблоны уведомлений
INSERT INTO notification_templates (code, title, body, channel) VALUES
    ('appointment_created',  'Новая запись на консультацию', 'Запись на {{date}} в {{time}} создана.',               'web'),
    ('appointment_reminder', 'Напоминание о консультации',   'Напоминаем: консультация {{date}} в {{time}}.',        'email'),
    ('appointment_canceled', 'Консультация отменена',        'Консультация на {{date}} отменена.',                   'web'),
    ('test_result_ready',    'Результаты теста готовы',      'Результаты теста «{{test_title}}» доступны в ЛК.',     'web'),
    ('qa_answered',          'Ответ на ваш вопрос',          'Психолог ответил на ваш вопрос.',                      'web'),
    ('new_qa_assigned',      'Новый вопрос',                 'Вам назначен новый вопрос от клиента.',                'web');

-- Политики конфиденциальности
INSERT INTO consents (policy_type, version, title, content, is_mandatory, published_at) VALUES
    ('privacy_policy',  1, 'Политика конфиденциальности v1',      'Текст политики конфиденциальности...',  TRUE, NOW()),
    ('data_processing', 1, 'Согласие на обработку ПДн v1',        'Текст согласия на обработку ПДн...',    TRUE, NOW()),
    ('test_consent',    1, 'Согласие на прохождение диагностики v1','Текст согласия на диагностику...',    TRUE, NOW());
