"""
Сервис публичной части кампаний (ADR-036): токен → кампания, сборка DTO без
ключа методики, отправка анкеты и ответов.
"""
from typing import Optional

from app.campaigns import storage, tokens
from app.campaigns.answers import AnswersInvalid  # noqa: F401  (ре-экспорт для routes)
from app.campaigns.storage import CampaignNotFound, ConsentOutdated  # noqa: F401
from app.student_verification.faculties import FACULTIES
from app.tests.profiles import ito_sobchik


def _hash_or_404(token: str) -> str:
    token_hash = tokens.lookup_hash(token)
    if token_hash is None:
        raise CampaignNotFound()
    return token_hash


def _instruction(test: dict) -> str:
    if test["scoring_profile"] == ito_sobchik.PROFILE:
        return ito_sobchik.INSTRUCTION
    return test["description"] or ""


def get_public_campaign(token: str) -> dict:
    data = storage.load_public(_hash_or_404(token))
    test = data["test"]
    return {
        "title": data["title"],
        "test_title": test["title"],
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
    return storage.submit(_hash_or_404(token), payload, ip=ip,
                          user_agent=user_agent)
