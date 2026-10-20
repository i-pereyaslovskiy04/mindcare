"""
Stage 5B-1 corrective — unit spy обоих production caller авто-привязки карточек:
A. auth.service.register_confirm  → actor = созданный/восстановленный student;
B. supervisor.service.create_student → actor = исходный staff (supervisor/admin),
   linked_cards_count остаётся int.
Реальная БД не используется (storage/notify/email замоканы).
"""
import app.auth.service as auth_service
import app.supervisor.service as sup_service
import app.appointments.service as appt_service


def test_register_confirm_links_with_student_actor(monkeypatch):
    monkeypatch.setattr(
        auth_service.storage, "register_confirm_atomic",
        lambda **kw: {"id": 42, "email": "x@donnu.ru", "role": "student"},
    )
    monkeypatch.setattr(
        "app.appointments.storage.link_unregistered_cards_to_user",
        lambda *a, **kw: [],
    )
    spy = {}
    monkeypatch.setattr(
        appt_service, "link_unregistered_cards_to_user",
        lambda *a, **kw: spy.update(args=a, kwargs=kw) or 0,
    )
    monkeypatch.setattr(
        "app.chat.system_publisher.publish_system_message", lambda **kw: None)

    auth_service.register_confirm(
        email="x@donnu.ru", code="123456",
        ip="203.0.113.7", user_agent="reg-ua",
    )
    assert spy["args"] == (42, "x@donnu.ru")
    assert spy["kwargs"]["actor_id"] == 42
    assert spy["kwargs"]["actor_role"] == "student"
    assert spy["kwargs"]["ip"] == "203.0.113.7"
    assert spy["kwargs"]["user_agent"] == "reg-ua"


def test_create_student_links_with_staff_actor_and_int_count(monkeypatch):
    monkeypatch.setattr(
        sup_service.storage, "create_student",
        lambda **kw: {"id": 77, "email": "y@donnu.ru", "full_name": "N",
                      "engagement": None},
    )
    spy = {}
    monkeypatch.setattr(
        appt_service, "link_unregistered_cards_to_user",
        lambda *a, **kw: (spy.update(args=a, kwargs=kw), 2)[1],
    )
    monkeypatch.setattr(
        "app.services.email_service.send_welcome_student", lambda **kw: None)
    monkeypatch.setattr(sup_service, "publish_system_message", lambda **kw: None)

    result = sup_service.create_student(
        full_name="N", email="y@donnu.ru", phone=None, psychologist_id=None,
        primary_concern=None, actor_id=9, actor_role="supervisor",
        ip="203.0.113.9", user_agent="staff-ua",
    )
    assert spy["args"] == (77, "y@donnu.ru")
    assert spy["kwargs"]["actor_id"] == 9
    assert spy["kwargs"]["actor_role"] == "supervisor"
    assert spy["kwargs"]["ip"] == "203.0.113.9"
    assert spy["kwargs"]["user_agent"] == "staff-ua"
    assert isinstance(result["linked_cards_count"], int)
    assert result["linked_cards_count"] == 2


def test_linking_diagnostics_redacted(monkeypatch, caplog):
    # Синтетическое исключение с ПДн/UUID/SQL/секретом: в лог попадают только
    # flow, phase=card_link и имя класса — без payload.
    import logging

    class _Leaky(RuntimeError):
        def __str__(self):
            return ("leak@secret.example 550e8400-e29b-41d4 "
                    "SELECT * FROM users; topsecret")

    monkeypatch.setattr(
        sup_service.storage, "create_student",
        lambda **kw: {"id": 77, "email": "y@donnu.ru", "full_name": "N",
                      "engagement": None},
    )

    def _boom(*a, **kw):
        raise _Leaky()
    monkeypatch.setattr(appt_service, "link_unregistered_cards_to_user", _boom)
    monkeypatch.setattr(
        "app.services.email_service.send_welcome_student", lambda **kw: None)
    monkeypatch.setattr(sup_service, "publish_system_message", lambda **kw: None)

    with caplog.at_level(logging.WARNING):
        sup_service.create_student(
            full_name="N", email="y@donnu.ru", phone=None, psychologist_id=None,
            primary_concern=None, actor_id=9, actor_role="supervisor",
            ip="203.0.113.9", user_agent="staff-ua",
        )
    text = caplog.text
    assert "phase=card_link" in text
    assert "_Leaky" in text
    for leak in ("leak@secret.example", "550e8400", "SELECT", "topsecret",
                 "y@donnu.ru", "203.0.113.9"):
        assert leak not in text


def test_register_confirm_linking_diagnostics_redacted(monkeypatch, caplog):
    import logging

    class _Leaky(RuntimeError):
        def __str__(self):
            return ("regleak@secret.example 660e8400-uuid "
                    "DELETE FROM cards; regsecret")

    monkeypatch.setattr(
        auth_service.storage, "register_confirm_atomic",
        lambda **kw: {"id": 42, "email": "x@donnu.ru", "role": "student"},
    )

    def _boom(*a, **kw):
        raise _Leaky()
    monkeypatch.setattr(appt_service, "link_unregistered_cards_to_user", _boom)
    monkeypatch.setattr(
        "app.chat.system_publisher.publish_system_message", lambda **kw: None)

    with caplog.at_level(logging.WARNING):
        auth_service.register_confirm(
            email="x@donnu.ru", code="123456",
            ip="203.0.113.7", user_agent="reg-ua",
        )
    text = caplog.text
    assert "phase=card_link" in text and "_Leaky" in text
    for leak in ("regleak@secret.example", "660e8400", "DELETE", "regsecret",
                 "x@donnu.ru", "203.0.113.7"):
        assert leak not in text
