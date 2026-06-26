"""update_diary_emotions_catalog

Обновляет справочник состояний дневника до профессионального набора из 12 позиций:
  - Деактивирует устаревшие: angry (злобно), light (легко) — is_active=false
  - Добавляет 4 новых: tense (напряжённо), irritated (раздражённо),
    low (подавленно), lonely (одиноко)
  - Пересортировывает активный каталог согласно новому порядку

Новый порядок активных состояний:
  1. calm        — спокойно
  2. joyful      — радостно
  3. inspired    — вдохновлённо
  4. focused     — сосредоточенно
  5. anxious     — тревожно
  6. tense       — напряжённо  (новое)
  7. irritated   — раздражённо (новое)
  8. sad         — грустно
  9. low         — подавленно  (новое)
 10. tired       — устало
 11. lonely      — одиноко     (новое)
 12. confused    — растерянно

Историческая целостность:
  Записи дневника с ключами angry/light в emotions_enc сохраняются зашифрованными.
  GET /api/diary/emotions не возвращает деактивированные ключи.
  Фронт показывает устаревшие ключи через LEGACY_EMOTION_LABELS (DiaryEntryItem.jsx).
  Новые записи НЕ могут использовать deprecated ключи (_validate_emotion_keys
  проверяет только is_active=True через get_all_emotion_keys()).

Revision ID: c3a7f8e2d1b9
Revises: b2e4d7f1a9c3
Create Date: 2026-06-25
"""
from alembic import op

revision = 'c3a7f8e2d1b9'
down_revision = 'b2e4d7f1a9c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Деактивировать устаревшие состояния (sort_order 99/98 — за пределами активного каталога)
    op.execute("UPDATE diary_emotions SET is_active = false, sort_order = 99 WHERE key = 'angry'")
    op.execute("UPDATE diary_emotions SET is_active = false, sort_order = 98 WHERE key = 'light'")

    # Обновить sort_order для существующих активных состояний (новый порядок)
    op.execute("UPDATE diary_emotions SET sort_order = 1  WHERE key = 'calm'")
    op.execute("UPDATE diary_emotions SET sort_order = 2  WHERE key = 'joyful'")
    op.execute("UPDATE diary_emotions SET sort_order = 3  WHERE key = 'inspired'")
    op.execute("UPDATE diary_emotions SET sort_order = 4  WHERE key = 'focused'")
    op.execute("UPDATE diary_emotions SET sort_order = 5  WHERE key = 'anxious'")
    op.execute("UPDATE diary_emotions SET sort_order = 8  WHERE key = 'sad'")
    op.execute("UPDATE diary_emotions SET sort_order = 10 WHERE key = 'tired'")
    op.execute("UPDATE diary_emotions SET sort_order = 12 WHERE key = 'confused'")

    # Добавить 4 новых активных состояния
    op.execute("""
        INSERT INTO diary_emotions (key, label, sort_order, is_active) VALUES
        ('tense',    'напряжённо',  6,  true),
        ('irritated','раздражённо', 7,  true),
        ('low',      'подавленно',  9,  true),
        ('lonely',   'одиноко',    11,  true)
    """)


def downgrade() -> None:
    # Удалить добавленные состояния
    op.execute("DELETE FROM diary_emotions WHERE key IN ('tense', 'irritated', 'low', 'lonely')")

    # Восстановить sort_order существующих состояний (исходный порядок из b2e4d7f1a9c3)
    op.execute("UPDATE diary_emotions SET sort_order = 1  WHERE key = 'calm'")
    op.execute("UPDATE diary_emotions SET sort_order = 2  WHERE key = 'joyful'")
    op.execute("UPDATE diary_emotions SET sort_order = 3  WHERE key = 'anxious'")
    op.execute("UPDATE diary_emotions SET sort_order = 4  WHERE key = 'sad'")
    op.execute("UPDATE diary_emotions SET sort_order = 5  WHERE key = 'tired'")
    op.execute("UPDATE diary_emotions SET sort_order = 7  WHERE key = 'inspired'")
    op.execute("UPDATE diary_emotions SET sort_order = 8  WHERE key = 'confused'")
    op.execute("UPDATE diary_emotions SET sort_order = 10 WHERE key = 'focused'")

    # Реактивировать устаревшие состояния
    op.execute("UPDATE diary_emotions SET is_active = true, sort_order = 6 WHERE key = 'angry'")
    op.execute("UPDATE diary_emotions SET is_active = true, sort_order = 9 WHERE key = 'light'")
