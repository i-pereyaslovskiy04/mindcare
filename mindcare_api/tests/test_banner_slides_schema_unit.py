"""
Unit-тесты Pydantic-схем banner_slides: title — единственное обязательное
текстовое поле, остальные (label/highlight/sub/image_uuid) опциональны.
Без БД.
"""
import pytest
from pydantic import ValidationError

from app.banner_slides.schemas import BannerSlideCreate, BannerSlideUpdate


class TestBannerSlideCreate:
    def test_title_required(self):
        with pytest.raises(ValidationError):
            BannerSlideCreate()

    def test_blank_title_rejected(self):
        with pytest.raises(ValidationError):
            BannerSlideCreate(title="")

    def test_title_only_is_valid(self):
        slide = BannerSlideCreate(title="Забота о вашей душевной гармонии")
        assert slide.title == "Забота о вашей душевной гармонии"
        assert slide.label is None
        assert slide.highlight is None
        assert slide.sub is None
        assert slide.image_uuid is None
        assert slide.display_order == 0
        assert slide.is_active is True
        assert slide.placement == "home"

    def test_placement_rejects_unknown_page(self):
        with pytest.raises(ValidationError):
            BannerSlideCreate(title="Заголовок", placement="unknown-page")

    def test_placement_accepts_services(self):
        slide = BannerSlideCreate(title="Заголовок", placement="services")
        assert slide.placement == "services"

    def test_all_optional_fields_can_be_set(self):
        slide = BannerSlideCreate(
            title="Заголовок",
            label="Метка",
            highlight="Акцент",
            sub="Подзаголовок",
            image_uuid="8e9c8b0a-1111-4b2c-9a3d-000000000000",
            link_url="/services",
            display_order=5,
            is_active=False,
        )
        assert slide.label == "Метка"
        assert slide.highlight == "Акцент"
        assert slide.sub == "Подзаголовок"
        assert slide.link_url == "/services"
        assert slide.display_order == 5
        assert slide.is_active is False

    def test_link_url_defaults_to_none(self):
        slide = BannerSlideCreate(title="Заголовок")
        assert slide.link_url is None


class TestBannerSlideUpdate:
    def test_empty_update_is_valid_noop(self):
        """PATCH {} не должен падать — exclude_unset делает его no-op в service."""
        update = BannerSlideUpdate()
        assert update.model_dump(exclude_unset=True) == {}

    def test_blank_title_rejected_when_present(self):
        with pytest.raises(ValidationError):
            BannerSlideUpdate(title="")

    def test_absent_title_does_not_raise(self):
        update = BannerSlideUpdate(sub="Только подзаголовок")
        assert "title" not in update.model_dump(exclude_unset=True)

    def test_only_is_active_can_be_set(self):
        update = BannerSlideUpdate(is_active=False)
        assert update.model_dump(exclude_unset=True) == {"is_active": False}

    def test_explicit_null_link_url_clears_it(self):
        """Явный null в PATCH — сигнал «убрать ссылку», в отличие от
        отсутствия ключа («не трогать»); exclude_unset различает эти случаи."""
        update = BannerSlideUpdate(link_url=None)
        assert update.model_dump(exclude_unset=True) == {"link_url": None}

    def test_absent_link_url_is_not_in_dump(self):
        update = BannerSlideUpdate(title="Новый заголовок")
        assert "link_url" not in update.model_dump(exclude_unset=True)

    def test_placement_rejects_unknown_page(self):
        with pytest.raises(ValidationError):
            BannerSlideUpdate(placement="unknown-page")
