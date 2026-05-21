"""
Единственный источник SQLAlchemy Base.

Все ORM-модели импортируют Base отсюда.
session.py импортирует Base отсюда и реэкспортирует для обратной совместимости.

Почему отдельный файл:
  - исключает циклические импорты (models/* → base, session → base)
  - гарантирует единственный экземпляр Base во всём приложении
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
