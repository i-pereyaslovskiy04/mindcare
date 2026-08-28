"""
Unit-тесты Pydantic-схем service_cards: title и description — обязательные
текстовые поля (в отличие от banner_slides, где sub опционален), benefits —
список строк с дефолтом []. Без БД.
"""
import pytest
from pydantic import ValidationError

from app.service_cards.schemas import ServiceCardCreate, ServiceCardUpdate


class TestServiceCardCreate:
    def test_title_required(self):
        with pytest.raises(ValidationError):
            ServiceCardCreate(description="Описание")

    def test_blank_title_rejected(self):
        with pytest.raises(ValidationError):
            ServiceCardCreate(title="", description="Описание")

    def test_description_required(self):
        with pytest.raises(ValidationError):
            ServiceCardCreate(title="Заголовок")

    def test_blank_description_rejected(self):
        with pytest.raises(ValidationError):
            ServiceCardCreate(title="Заголовок", description="")

    def test_title_and_description_only_is_valid(self):
        card = ServiceCardCreate(title="Заголовок", description="Описание услуги")
        assert card.title == "Заголовок"
        assert card.description == "Описание услуги"
        assert card.benefits == []
        assert card.image_uuid is None
        assert card.link_url is None
        assert card.display_order == 0
        assert card.is_active is True

    def test_benefits_accepts_list_of_strings(self):
        card = ServiceCardCreate(
            title="Заголовок", description="Описание",
            benefits=["Пункт 1", "Пункт 2", "Пункт 3"],
        )
        assert card.benefits == ["Пункт 1", "Пункт 2", "Пункт 3"]

    def test_all_optional_fields_can_be_set(self):
        card = ServiceCardCreate(
            title="Заголовок",
            description="Описание",
            benefits=["Пункт 1"],
            image_uuid="8e9c8b0a-1111-4b2c-9a3d-000000000000",
            link_url="/services",
            display_order=5,
            is_active=False,
        )
        assert card.image_uuid == "8e9c8b0a-1111-4b2c-9a3d-000000000000"
        assert card.link_url == "/services"
        assert card.display_order == 5
        assert card.is_active is False

    def test_link_url_defaults_to_none(self):
        card = ServiceCardCreate(title="Заголовок", description="Описание")
        assert card.link_url is None


class TestServiceCardUpdate:
    def test_empty_update_is_valid_noop(self):
        """PATCH {} не должен падать — exclude_unset делает его no-op в service."""
        update = ServiceCardUpdate()
        assert update.model_dump(exclude_unset=True) == {}

    def test_blank_title_rejected_when_present(self):
        with pytest.raises(ValidationError):
            ServiceCardUpdate(title="")

    def test_blank_description_rejected_when_present(self):
        with pytest.raises(ValidationError):
            ServiceCardUpdate(description="")

    def test_absent_title_does_not_raise(self):
        update = ServiceCardUpdate(description="Только описание")
        assert "title" not in update.model_dump(exclude_unset=True)

    def test_only_is_active_can_be_set(self):
        update = ServiceCardUpdate(is_active=False)
        assert update.model_dump(exclude_unset=True) == {"is_active": False}

    def test_explicit_null_link_url_clears_it(self):
        """Явный null в PATCH — сигнал «убрать ссылку», в отличие от
        отсутствия ключа («не трогать»); exclude_unset различает эти случаи."""
        update = ServiceCardUpdate(link_url=None)
        assert update.model_dump(exclude_unset=True) == {"link_url": None}

    def test_absent_link_url_is_not_in_dump(self):
        update = ServiceCardUpdate(title="Новый заголовок")
        assert "link_url" not in update.model_dump(exclude_unset=True)

    def test_explicit_null_title_present_in_dump(self):
        """Схема допускает null (не 422 на уровне Pydantic) — отклонять его
        обязан service-слой (см. ServiceCardError NOT NULL guard); здесь
        фиксируем только то, что exclude_unset различает null от отсутствия."""
        update = ServiceCardUpdate(title=None)
        assert update.model_dump(exclude_unset=True) == {"title": None}

    def test_benefits_can_be_updated(self):
        update = ServiceCardUpdate(benefits=["Новый пункт"])
        assert update.model_dump(exclude_unset=True) == {"benefits": ["Новый пункт"]}
