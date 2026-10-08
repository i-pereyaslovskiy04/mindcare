"""
ADR-029 — unit-тесты подтверждения статуса студента ДонГУ и outbox
system-сообщений БЕЗ подключения к БД.

Покрывает:
  * каталог факультетов: ровно 12, стабильные коды, точные подписи, порядок;
  * схемы: все коды каталога, произвольный факультет, ведущие нули, trim,
    пустое/длинное значение, управляющие символы, лишние поля, пояснение
    отказа;
  * тексты уведомлений: дословно, без HTML, ссылка на раздел, форматы ключей;
  * точные контракты шести EventSpec;
  * create_system_message: дубль — ТОЛЬКО ux_chat_messages_event_key, иное
    IntegrityError пробрасывается;
  * deliver_intent/run_pending/deliver_by_key_soft: исходы, отметка delivered
    только после успешного publisher, ошибка чтения outbox не маскируется,
    диагностика без ключей/id/текста.
"""
import logging
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.audit.contracts import (
    ActorPolicy, Destination, FailurePolicy, Outcome, TargetPolicy, TxMode,
)
from app.audit.registry import REGISTRY
from app.notifications import service as outbox_service
from app.notifications import storage as outbox_storage
from app.notifications.templates import (
    MESSAGE_TEMPLATES, STUDENT_VERIFICATION_APPROVED, STUDENT_VERIFICATION_INVITE,
    STUDENT_VERIFICATION_REJECTED, invite_event_key, result_event_key,
)
from app.student_verification.faculties import (
    FACULTIES, FACULTY_CODES, faculty_label,
)
from app.student_verification.schemas import (
    REJECTION_REASON_MAX_LEN, TICKET_NUMBER_MAX_LEN, RejectIn, SubmitIn,
)

# ── каталог ───────────────────────────────────────────────────────────────────

EXPECTED_FACULTIES = (
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


def test_catalog_is_exactly_twelve_stable_faculties_in_order():
    assert FACULTIES == EXPECTED_FACULTIES
    assert len(FACULTY_CODES) == 12 == len(set(FACULTY_CODES))
    assert faculty_label("law") == "Юридический факультет"
    assert faculty_label("unknown_code") is None


# ── схемы ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", [c for c, _ in EXPECTED_FACULTIES])
def test_every_catalog_code_is_accepted(code):
    assert SubmitIn(faculty_code=code, ticket_number="1").faculty_code == code


@pytest.mark.parametrize("code", ["", "Юридический факультет", "LAW", "medicine", "law "])
def test_arbitrary_faculty_is_rejected(code):
    with pytest.raises(ValidationError):
        SubmitIn(faculty_code=code, ticket_number="1")


def test_leading_zeros_are_preserved_and_value_is_trimmed():
    assert SubmitIn(faculty_code="law", ticket_number="  000123\t").ticket_number == "000123"


@pytest.mark.parametrize("value", ["", "   ", "\t \t"])
def test_empty_ticket_is_rejected(value):
    with pytest.raises(ValidationError):
        SubmitIn(faculty_code="law", ticket_number=value)


def test_ticket_length_bound():
    ok = "0" * TICKET_NUMBER_MAX_LEN
    assert SubmitIn(faculty_code="law", ticket_number=ok).ticket_number == ok
    with pytest.raises(ValidationError):
        SubmitIn(faculty_code="law", ticket_number="0" * (TICKET_NUMBER_MAX_LEN + 1))


@pytest.mark.parametrize("value", ["12\n34", "12\x0034", "12\x7f"])
def test_control_characters_are_rejected(value):
    with pytest.raises(ValidationError):
        SubmitIn(faculty_code="law", ticket_number=value)


def test_ticket_must_be_a_string_and_extra_fields_are_forbidden():
    with pytest.raises(ValidationError):
        SubmitIn(faculty_code="law", ticket_number=123)
    with pytest.raises(ValidationError):
        SubmitIn(faculty_code="law", ticket_number="1", user_id=5)


def test_reject_reason_is_required_trimmed_and_bounded():
    assert RejectIn(reason="  Неверный номер  ").reason == "Неверный номер"
    for bad in ("", "   "):
        with pytest.raises(ValidationError):
            RejectIn(reason=bad)
    with pytest.raises(ValidationError):
        RejectIn(reason="x" * (REJECTION_REASON_MAX_LEN + 1))


# ── уведомления ───────────────────────────────────────────────────────────────

INVITE_TEXT = (
    "Вы можете подтвердить, что являетесь студентом Донецкого "
    "государственного университета. Выберите факультет и укажите номер "
    "студенческого билета в настройках аккаунта.\n\n"
    "Открыть раздел: /student/settings#student-verification"
)


def test_message_texts_are_fixed_plain_and_link_to_the_section():
    assert MESSAGE_TEMPLATES[STUDENT_VERIFICATION_INVITE] == INVITE_TEXT
    assert MESSAGE_TEMPLATES[STUDENT_VERIFICATION_APPROVED] == (
        "Ваш статус студента ДонГУ подтверждён."
    )
    assert MESSAGE_TEMPLATES[STUDENT_VERIFICATION_REJECTED].startswith(
        "Подтверждение статуса студента ДонГУ отклонено. Посмотрите пояснение "
        "и исправьте данные в настройках."
    )
    for text in MESSAGE_TEMPLATES.values():
        assert "<" not in text and ">" not in text


def test_event_keys_stable_per_user_and_per_request():
    assert invite_event_key(42) == "student_verification_invite:user:42"
    assert invite_event_key("42") == invite_event_key(42)
    uid = "1b4e28ba-2fa1-11d2-883f-0016d3cca427"
    assert result_event_key(uid) == f"student_verification_result:{uid}"


def test_enqueue_rejects_unknown_message_code_before_write():
    db = SimpleNamespace(execute=lambda *a, **k: pytest.fail("must not write"))
    with pytest.raises(ValueError):
        outbox_storage.enqueue_in_tx(
            db, recipient_id=1, event_key="k", message_code="free_text",
        )


# ── EventSpec ─────────────────────────────────────────────────────────────────

_ENTITY = "student_verification_request"


@pytest.mark.parametrize("name,roles,tx,policy", [
    ("student_verification_submitted", {"student"}, TxMode.ATOMIC, FailurePolicy.RAISE),
    ("student_verification_approved", {"supervisor"}, TxMode.ATOMIC, FailurePolicy.RAISE),
    ("student_verification_rejected", {"supervisor"}, TxMode.ATOMIC, FailurePolicy.RAISE),
    ("student_verification_content_read", {"supervisor"},
     TxMode.INDEPENDENT, FailurePolicy.RAISE),
])
def test_success_event_contracts(name, roles, tx, policy):
    spec = REGISTRY[name]
    assert spec.destination is Destination.AUDIT_LOG
    assert spec.actor_policy is ActorPolicy.USER_REQUIRED
    assert spec.allowed_actor_roles == frozenset(roles)
    assert spec.target_policy is TargetPolicy.REQUIRED
    assert spec.entity_type == _ENTITY
    assert spec.allowed_outcomes == frozenset({Outcome.SUCCESS})
    assert spec.allowed_failure_codes == frozenset()
    assert dict(spec.metadata_schema) == {}
    assert spec.tx_mode is tx and spec.failure_policy is policy


@pytest.mark.parametrize("name,roles,codes", [
    ("student_verification_submit_failed",
     {"student", "psychologist", "supervisor", "admin"},
     {"verification_not_allowed", "impersonation_forbidden",
      "verification_pending_exists", "already_verified", "account_inactive"}),
    ("student_verification_review_failed", {"supervisor"},
     {"verification_not_found", "self_review_forbidden", "reviewer_not_allowed",
      "verification_already_decided", "account_inactive"}),
])
def test_failure_event_contracts(name, roles, codes):
    spec = REGISTRY[name]
    assert spec.destination is Destination.AUDIT_LOG
    assert spec.allowed_actor_roles == frozenset(roles)
    assert spec.target_policy is TargetPolicy.FORBIDDEN and spec.entity_type is None
    assert spec.allowed_outcomes == frozenset({Outcome.FAILURE})
    assert spec.allowed_failure_codes == frozenset(codes)
    assert dict(spec.metadata_schema) == {}
    assert spec.tx_mode is TxMode.INDEPENDENT
    assert spec.failure_policy is FailurePolicy.SOFT


def test_error_codes_match_registry_allowlists():
    from app.student_verification import errors
    submit = REGISTRY["student_verification_submit_failed"].allowed_failure_codes
    review = REGISTRY["student_verification_review_failed"].allowed_failure_codes
    for cls in (errors.VerificationNotAllowed, errors.ImpersonationForbidden,
                errors.VerificationPendingExists, errors.AlreadyVerified,
                errors.AccountInactive):
        assert cls.code in submit
    for cls in (errors.VerificationNotFound, errors.SelfReviewForbidden,
                errors.ReviewerNotAllowed, errors.VerificationAlreadyDecided,
                errors.AccountInactive):
        assert cls.code in review


# ── create_system_message: классификация IntegrityError ───────────────────────

def _integrity(constraint_name):
    orig = SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint_name))
    return IntegrityError("INSERT", {}, orig)


class _FakeDb:
    def __init__(self, exc):
        self._exc = exc
        self.rolled_back = False
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def add(self, _):
        pass

    def flush(self):
        raise self._exc

    def rollback(self):
        self.rolled_back = True

    def commit(self):
        self.committed = True


def _patch_chat_storage(monkeypatch, exc):
    from app.chat import storage as chat_storage
    db = _FakeDb(exc)
    monkeypatch.setattr(
        chat_storage, "get_or_create_system_conversation",
        lambda rid: (SimpleNamespace(id=7), False),
    )
    monkeypatch.setattr(chat_storage, "SessionLocal", lambda: db)
    monkeypatch.setattr(chat_storage, "encrypt_text", lambda t: "enc:v1:x")
    return chat_storage, db


def test_duplicate_event_key_is_the_only_integrity_error_treated_as_published(monkeypatch):
    chat_storage, db = _patch_chat_storage(
        monkeypatch, _integrity("ux_chat_messages_event_key"),
    )
    result, created = chat_storage.create_system_message(1, event_key="k", text="t")
    assert result == {"created": False, "conversation_id": 7}
    assert created is False and db.rolled_back and not db.committed


@pytest.mark.parametrize("name", [None, "ck_chat_messages_kind_sender",
                                  "chat_messages_conversation_id_fkey"])
def test_other_integrity_errors_are_reraised(monkeypatch, name):
    chat_storage, db = _patch_chat_storage(monkeypatch, _integrity(name))
    with pytest.raises(IntegrityError):
        chat_storage.create_system_message(1, event_key="k", text="t")
    assert db.rolled_back and not db.committed


def test_publisher_turns_foreign_integrity_error_into_none_without_details(
    monkeypatch, capsys,
):
    from app.chat import system_publisher
    _patch_chat_storage(monkeypatch, _integrity("other_constraint"))
    out = system_publisher.publish_system_message(
        5, "student_verification_invite:user:5", "secret-text",
    )
    assert out is None
    err = capsys.readouterr().err
    assert "error=IntegrityError" in err
    assert "student_verification_invite" not in err and "secret-text" not in err


# ── outbox: исходы доставки ──────────────────────────────────────────────────

_INTENT = {"id": 11, "recipient_id": 5,
           "event_key": "student_verification_invite:user:5",
           "message_code": STUDENT_VERIFICATION_INVITE}


@pytest.fixture
def outbox(monkeypatch):
    calls = {"publish": [], "mark": [], "attempt": []}
    state = {"publish": {"created": True, "conversation_id": 1},
             "mark_exc": None, "read_exc": None, "intents": [dict(_INTENT)]}

    def _publish(**kw):
        calls["publish"].append(kw)
        if isinstance(state["publish"], Exception):
            raise state["publish"]
        return state["publish"]

    def _mark(intent_id):
        calls["mark"].append(intent_id)
        if state["mark_exc"]:
            raise state["mark_exc"]
        return True

    def _read(limit):
        if state["read_exc"]:
            raise state["read_exc"]
        return state["intents"]

    monkeypatch.setattr("app.chat.system_publisher.publish_system_message", _publish)
    monkeypatch.setattr(outbox_storage, "mark_delivered", _mark)
    monkeypatch.setattr(outbox_storage, "record_attempt",
                        lambda i: calls["attempt"].append(i))
    monkeypatch.setattr(outbox_storage, "get_undelivered", _read)
    monkeypatch.setattr(outbox_storage, "get_undelivered_by_key",
                        lambda rid, key: dict(_INTENT))
    return calls, state


def test_delivered_only_after_successful_publish(outbox):
    calls, _ = outbox
    assert outbox_service.deliver_intent(dict(_INTENT)) is outbox_service.DeliveryOutcome.DELIVERED
    assert calls["publish"] == [{
        "recipient_id": 5, "event_key": _INTENT["event_key"],
        "text": MESSAGE_TEMPLATES[STUDENT_VERIFICATION_INVITE],
    }]
    assert calls["mark"] == [11] and calls["attempt"] == []


def test_already_published_message_counts_as_delivered(outbox):
    calls, state = outbox
    state["publish"] = {"created": False, "conversation_id": 1}
    assert outbox_service.deliver_intent(dict(_INTENT)) is outbox_service.DeliveryOutcome.DELIVERED
    assert calls["mark"] == [11]


@pytest.mark.parametrize("failure", [None, RuntimeError("boom")])
def test_publish_failure_is_not_marked(outbox, failure):
    calls, state = outbox
    state["publish"] = failure
    assert outbox_service.deliver_intent(dict(_INTENT)) is outbox_service.DeliveryOutcome.PUBLISH_FAILED
    assert calls["mark"] == [] and calls["attempt"] == [11]


def test_mark_failure_is_reported(outbox):
    calls, state = outbox
    state["mark_exc"] = RuntimeError("db down")
    assert outbox_service.deliver_intent(dict(_INTENT)) is outbox_service.DeliveryOutcome.MARK_FAILED
    assert len(calls["publish"]) == 1


def test_unknown_message_code_never_publishes(outbox):
    calls, _ = outbox
    intent = dict(_INTENT, message_code="not_a_template")
    assert outbox_service.deliver_intent(intent) is outbox_service.DeliveryOutcome.PUBLISH_FAILED
    assert calls["publish"] == [] and calls["attempt"] == [11]


def test_run_pending_counts_every_non_delivered_outcome(outbox):
    _, state = outbox
    state["intents"] = [dict(_INTENT), dict(_INTENT, id=12)]
    state["publish"] = None
    stats = outbox_service.run_pending(10)
    assert (stats.found, stats.delivered, stats.failed) == (2, 0, 2)


def test_run_pending_does_not_mask_read_errors_as_empty_queue(outbox):
    _, state = outbox
    state["read_exc"] = RuntimeError("outbox unreachable")
    with pytest.raises(RuntimeError):
        outbox_service.run_pending(10)


def test_post_commit_delivery_is_soft_and_logs_no_identifiers(
    monkeypatch, caplog,
):
    def _boom(*a, **k):
        raise RuntimeError("student_verification_invite:user:5 secret")
    monkeypatch.setattr(outbox_storage, "get_undelivered_by_key", _boom)
    with caplog.at_level(logging.WARNING):
        assert outbox_service.deliver_by_key_soft(5, "student_verification_invite:user:5") is None
    text = caplog.text
    assert "phase=post_commit error=RuntimeError" in text
    assert "student_verification_invite" not in text and "secret" not in text
