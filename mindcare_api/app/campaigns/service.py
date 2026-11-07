"""
Сервис публичной части кампаний (ADR-036): токен → кампания, сборка DTO без
ключа методики, отправка анкеты и ответов.

Сроки и кодовое слово (ТЗ этапа 2, §6): до начала — CampaignNotStarted,
после окончания — как закрытая. Если задано кодовое слово, GET отдаёт только
название и признак access_code_required (без вопросов и согласия); анкету
открывает unlock с верным словом, отправка проверяет слово ещё раз.
bcrypt — вне транзакций.
"""
from typing import Optional

from app.campaigns import access, storage, tokens
from app.campaigns.answers import AnswersInvalid  # noqa: F401  (ре-экспорт для routes)
from app.campaigns.storage import (  # noqa: F401  (ре-экспорт для routes)
    AccessCodeWrong, CampaignNotFound, CampaignNotStarted, ConsentOutdated,
)
from app.student_verification.faculties import FACULTIES
from app.tests import rules as test_rules


def _hash_or_404(token: str) -> str:
    token_hash = tokens.lookup_hash(token)
    if token_hash is None:
        raise CampaignNotFound()
    return token_hash


def _instruction(test: dict) -> str:
    rules = test_rules.parse(test["scoring_rules"])
    if rules is not None and rules.instruction:
        return rules.instruction
    return test["description"] or ""


def get_public_campaign(token: str, access_code: Optional[str] = None,
                        *, unlock: bool = False) -> dict:
    """GET (unlock=False): при заданном кодовом слове — только «замок».
    unlock=True: слово обязано совпасть, иначе AccessCodeWrong."""
    data = storage.load_public(_hash_or_404(token))
    test = data["test"]
    code_hash = data["access_code_hash"]
    if code_hash is not None:
        if not unlock:
            return {"title": data["title"], "test_title": test["title"],
                    "access_code_required": True, "closes_at": data["closes_at"],
                    "instruction": "", "consent": None, "faculties": [], "questions": []}
        if not access.code_matches(access_code, code_hash):
            raise AccessCodeWrong()
    return {
        "title": data["title"],
        "test_title": test["title"],
        "access_code_required": code_hash is not None,
        "closes_at": data["closes_at"],
        "instruction": _instruction(test),
        "consent": data["consent"],
        "faculties": [{"code": c, "label": label} for c, label in FACULTIES],
        # Только тексты: value_score/config/шкалы не отдаются (ключ методики).
        "questions": [
            {"id": q["id"], "number": q["number"], "text": q["text"],
             "options": [{"id": o["id"], "text": o["text"]} for o in q["options"]]}
            for q in test["questions"]
        ],
    }


def submit(token: str, payload: dict, *, ip: Optional[str],
           user_agent: Optional[str]) -> str:
    token_hash = _hash_or_404(token)
    code = payload.pop("access_code", None)
    try:
        code_hash = storage.access_code_hash(token_hash)
    except (CampaignNotFound, CampaignNotStarted):
        # Решает транзакция отправки: повтор принятого ответа остаётся 200
        # и после закрытия кампании; иначе — тот же 404/409.
        code_hash = None
    if code_hash is not None and not access.code_matches(code, code_hash):
        raise AccessCodeWrong()
    return storage.submit(token_hash, payload, ip=ip, user_agent=user_agent,
                          verified_code_hash=code_hash)
