from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- DATABASE ---
    DATABASE_URL: str
    # --- AUTH ---
    SESSION_EXPIRE_DAYS: int = 7
    # --- EMAIL ---
    EMAIL_MODE: str = "dev"   # "dev" | "smtp"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    # SMTP_TLS=True  → STARTTLS (port 587). Cannot combine with SMTP_SSL.
    # SMTP_SSL=True  → implicit SSL (port 465). Cannot combine with SMTP_TLS.
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    # --- MEDIA ---
    NEWS_IMAGE_MAX_SIZE_MB: int = 20
    # Аудио/видео в вопросах тестов (без транскодирования и извлечения длительности)
    MEDIA_AV_MAX_SIZE_MB: int = 50
    # --- CHAT FILES ---
    CHAT_FILE_MAX_SIZE_MB: int = 20
    CHAT_FILE_MAX_FILES_PER_MESSAGE: int = 5
    # Относительный путь к private-хранилищу файлов чата (от mindcare_api/).
    # Не должен пересекаться с media/uploads/ (публичные изображения новостей).
    # Nginx/StaticFiles НЕ должен обслуживать этот путь напрямую.
    CHAT_FILE_STORAGE_DIR: str = "storage/private/chat_attachments"
    # 'local_private' — локальная FS без публичного доступа (MVP).
    # 's3' — будущий S3/MinIO backend (не реализован).
    CHAT_FILE_STORAGE_BACKEND: str = "local_private"
    # --- CORS ---
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    # --- SOCIAL AUTH (Stage Social Auth 2B; не секреты) ---
    # База redirect_uri провайдера: {base}/api/auth/oauth/{provider}/callback.
    # В dev — напрямую backend :8000: CRA-прокси не проксирует GET-навигацию
    # с Accept: text/html (отдал бы index.html). https:// включает Secure у
    # state-cookie. Хост не смешивать с 127.0.0.1 — cookie привязан к хосту.
    OAUTH_CALLBACK_BASE_URL: str = "http://localhost:8000"
    # Фиксированная страница фронтенда после callback; результат — во fragment.
    OAUTH_FRONTEND_CALLBACK_URL: str = "http://localhost:3000/auth/callback"
    # --- YANDEX ID (Stage Social Auth 3A) ---
    # Адаптер регистрируется только при ENABLED=true и непустом CLIENT_ID
    # (app/oauth/providers/bootstrap.py); иначе /oauth/yandex/* → 404, остальной
    # MindCare стартует как обычно. ClientID не секрет (виден в authorize URL), но
    # свой у каждого окружения (DEV/PROD — разные приложения Яндекс OAuth).
    # client_secret НЕ используется: PKCE S256 + code_verifier.
    YANDEX_OAUTH_ENABLED: bool = False
    YANDEX_OAUTH_CLIENT_ID: str = ""
    # --- VK ID (Stage Social Auth VK-1A) ---
    # То же правило регистрации адаптера, что у Яндекса. CLIENT_ID — «ID
    # приложения» VK ID (не секрет). Защищённый и сервисный ключи НЕ
    # используются: публичный клиент, PKCE S256.
    VK_OAUTH_ENABLED: bool = False
    VK_OAUTH_CLIENT_ID: str = ""
    # Необязательная база redirect_uri только для VK (пусто → общий
    # OAUTH_CALLBACK_BASE_URL). Нужна, когда доверенный Redirect URL приложения
    # VK зарегистрирован на другом порту, чем у Яндекса (DEV: http://localhost —
    # порт 80). Схема обязана совпадать с OAUTH_CALLBACK_BASE_URL (от неё
    # зависит Secure у общего state-cookie).
    VK_OAUTH_CALLBACK_BASE_URL: str = ""
    # --- ENCRYPTION ---
    DATA_ENCRYPTION_KEY: str | None = None
    # --- APP ---
    # DEBUG is a boolean flag only (true/false, 1/0, yes/no, on/off).
    # Use ENV for environment names — do not put "release"/"production" into DEBUG.
    DEBUG: bool = False
    ENV: str = "production"  # development | staging | production | release

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",   # игнорирует лишние переменные из .env
    )


settings = Settings()
SESSION_EXPIRE_DAYS = settings.SESSION_EXPIRE_DAYS

# Допустимые MIME-типы для chat attachments (Stage 32b).
# Не настраивается через .env — allowlist должен быть явно утверждён в коде.
# Upload-валидация (magic bytes check) реализуется в Stage 32c.
CHAT_FILE_ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
    # Изображения (SVG запрещён — может содержать скрипты)
    "image/jpeg",
    "image/png",
    "image/webp",
    # Документы — Word
    "application/pdf",
    "application/msword",                                                          # .doc
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",    # .docx
    # Документы — Excel
    "application/vnd.ms-excel",                                                   # .xls
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",          # .xlsx
    # Документы — PowerPoint
    "application/vnd.ms-powerpoint",                                              # .ppt
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
    # Текст
    "text/plain",
    # Архивы — отложены (pending: zip/rar могут содержать исполняемые файлы)
})
