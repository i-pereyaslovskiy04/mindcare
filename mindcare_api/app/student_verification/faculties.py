"""
Каталог факультетов ДонГУ — ЕДИНСТВЕННЫЙ источник (ADR-029).

Код — стабильный машинный идентификатор: хранится в
student_verification_requests.faculty_code и в API; подпись — только для UI.
Коды не переименовывать: по ним читаются уже поданные заявки. Порядок —
порядок показа в форме. Backend принимает только коды отсюда (schemas.SubmitIn).
"""
from types import MappingProxyType
from typing import Optional

FACULTIES: tuple[tuple[str, str], ...] = (
    ("math_it", "Факультет математики и информационных технологий"),
    ("physics_technology", "Физико-технический факультет"),
    ("chemistry", "Химический факультет"),
    ("biology", "Биологический факультет"),
    ("history", "Исторический факультет"),
    ("philology", "Филологический факультет"),
    ("foreign_languages", "Факультет иностранных языков"),
    ("economics", "Экономический факультет"),
    ("accounting_finance", "Учетно-финансовый факультет"),
    ("law", "Юридический факультет"),
    ("pedagogy", "Институт педагогики"),
    ("physical_culture_sport", "Институт физической культуры и спорта"),
)

FACULTY_LABELS = MappingProxyType(dict(FACULTIES))
FACULTY_CODES: tuple[str, ...] = tuple(code for code, _ in FACULTIES)


def faculty_label(code: str) -> Optional[str]:
    """Подпись по коду; None — код вне текущего каталога (историческая строка)."""
    return FACULTY_LABELS.get(code)


def faculty_dto(code: str) -> dict:
    return {"code": code, "label": faculty_label(code)}


if len(FACULTY_LABELS) != len(FACULTIES):   # fail-fast на импорте
    raise RuntimeError("duplicate faculty code in catalog")
