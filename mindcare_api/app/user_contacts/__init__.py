"""
Контакты пользователя (ADR-032): дополнительные способы связи владельца
аккаунта, хранимые зашифрованной коллекцией с версией.

  routes.py       — GET/PUT /api/auth/profile/contacts (только владелец);
  routes_staff.py — GET /api/staff/users/{uuid}/contacts (психолог/супервизор);
  service.py      — бизнес-логика БЕЗ FastAPI/HTTP (доменные ошибки);
  storage.py      — весь SQLAlchemy и шифрование;
  validators.py   — чистая нормализация/валидация элементов;
  catalog.py      — типы, сервисы, лимиты (единственный источник).
"""
