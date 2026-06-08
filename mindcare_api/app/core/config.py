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
    # --- MEDIA ---
    NEWS_IMAGE_MAX_SIZE_MB: int = 20
    # --- APP ---
    DEBUG: bool = False
    ENV: str = "production"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",   # игнорирует лишние переменные из .env
    )


settings = Settings()
SESSION_EXPIRE_DAYS = settings.SESSION_EXPIRE_DAYS
