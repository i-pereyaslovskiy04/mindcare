"""
Pydantic-схемы модуля психодиагностики (Этап A — admin CRUD конструктора теста).

Тест редактируется как единая вложенная структура: тест + вопросы + варианты +
пороги интерпретации. Это соответствует UI-конструктору (одна форма — один сабмит).

Ограничения (см. docs/MODULES/psychodiagnostics-spec-draft.md):
  - scoring: sum / average / weighted (weighted — взвешенная сумма по
    config["weight"]). Колонка tests.scoring — свободный VARCHAR(20) без
    CHECK/enum, ограничение задаётся ТОЛЬКО здесь. custom не поддержан (нет
    спецификации);
  - question_type: single_choice / multiple_choice / scale / free_text
    (free_text хранится, но в скоринг не входит).
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import field_validator, BaseModel, Field

from app.tests.rules import ScoringRulesV1

# Подмножества значений свободных VARCHAR-колонок БД (ограничение только тут)
ScoringMethod = Literal["sum", "average", "weighted"]
QuestionType  = Literal["single_choice", "multiple_choice", "scale", "free_text"]
# Moderation workflow (Этап F). При создании admin/supervisor допустимы только
# draft/published (in_review/needs_changes — результат переходов, не выставляются напрямую).
TestStatus       = Literal["draft", "in_review", "published", "needs_changes"]
TestCreateStatus = Literal["draft", "published"]


# ── медиа в вопросах/вариантах (изображения) ──────────────────────────────────

class MediaRef(BaseModel):
    """
    Ссылка на изображение из медиатеки. Автор адресует его по UUID (media_files.uuid);
    backend резолвит UUID → media_files.id при сохранении. caption используется
    только для вопроса (alt/подпись); у варианта поле игнорируется (декоративен).
    """
    media_uuid: str           = Field(min_length=1)
    caption:    Optional[str] = None


# ── вложенные create-схемы ────────────────────────────────────────────────────

class OptionCreate(BaseModel):
    option_text:  str = Field(min_length=1)
    option_order: int = Field(ge=0)
    value_score:  int = 0
    media:        list[MediaRef] = Field(default_factory=list)


class QuestionCreate(BaseModel):
    question_text:  str           = Field(min_length=1)
    question_order: int           = Field(ge=0)
    question_type:  QuestionType  = "single_choice"
    is_required:    bool          = True
    config:         dict          = Field(default_factory=dict)
    media:          list[MediaRef]     = Field(default_factory=list)
    options:        list[OptionCreate] = Field(default_factory=list)


class InterpretationCreate(BaseModel):
    scale_name:     Optional[str] = Field(default=None, max_length=100)
    min_score:      int
    max_score:      int
    label:          str           = Field(min_length=1, max_length=255)
    recommendation: Optional[str] = None


# ── create / update теста ─────────────────────────────────────────────────────

class TestCreate(BaseModel):
    title:          str           = Field(min_length=1, max_length=255)
    description:    Optional[str] = None
    scoring:        ScoringMethod = "sum"
    max_score:      Optional[int] = None
    time_limit_min: Optional[int] = Field(default=None, ge=0)
    is_active:      bool          = True
    status:         TestCreateStatus = "published"
    shuffle_questions: bool       = False
    shuffle_options:   bool       = False
    # ADR-037: правила обработки и флаг «только по ссылке» (вне каталога).
    scoring_rules:  Optional[ScoringRulesV1] = None
    campaign_only:  bool          = False
    category_ids:   list[int]     = Field(default_factory=list)
    tag_uuids:      list[str]     = Field(default_factory=list)
    questions:      list[QuestionCreate]       = Field(default_factory=list)
    interpretations: list[InterpretationCreate] = Field(default_factory=list)


class TestUpdate(BaseModel):
    """Частичное обновление. Вложенные коллекции заменяются целиком, если переданы."""
    title:          Optional[str]           = Field(default=None, min_length=1, max_length=255)
    description:    Optional[str]           = None
    scoring:        Optional[ScoringMethod] = None
    max_score:      Optional[int]           = None
    time_limit_min: Optional[int]           = Field(default=None, ge=0)
    is_active:      Optional[bool]          = None
    shuffle_questions: Optional[bool]       = None
    shuffle_options:   Optional[bool]       = None
    # ADR-037: явный null — убрать правила; ключ не передан — не менять.
    scoring_rules:  Optional[ScoringRulesV1] = None
    campaign_only:  Optional[bool]          = None
    category_ids:   Optional[list[int]]     = None
    tag_uuids:      Optional[list[str]]     = None
    questions:      Optional[list[QuestionCreate]]       = None
    interpretations: Optional[list[InterpretationCreate]] = None


# ── read-схемы ────────────────────────────────────────────────────────────────

class CategoryRef(BaseModel):
    id:   int
    name: str


class TagRef(BaseModel):
    uuid: str
    name: str


class MediaOut(BaseModel):
    """Медиа вопроса/варианта в read-выдаче. url = media_files.file_path;
    kind (image/audio/video) — по media_files.file_type, фронт выбирает тег."""
    uuid:    str
    url:     str
    kind:    str           = "image"
    caption: Optional[str] = None


class OptionRead(BaseModel):
    id:           int
    option_text:  str
    option_order: int
    value_score:  int
    media:        list[MediaOut] = Field(default_factory=list)


class QuestionRead(BaseModel):
    id:             int
    question_text:  str
    question_order: int
    question_type:  str
    is_required:    bool
    config:         dict
    media:          list[MediaOut] = Field(default_factory=list)
    options:        list[OptionRead]


class InterpretationRead(BaseModel):
    id:             int
    scale_name:     Optional[str]
    min_score:      int
    max_score:      int
    label:          str
    recommendation: Optional[str]


# ── анализ порогов интерпретации (предпросмотр в конструкторе) ────────────────

class TestAnalyzeIn(BaseModel):
    """
    Несохранённое дерево теста для анализа. Отдельная схема, а не TestCreate:
    в конструкторе название может быть ещё пустым, а анализ от него не зависит.
    """
    scoring:         ScoringMethod              = "sum"
    questions:       list[QuestionCreate]       = Field(default_factory=list)
    interpretations: list[InterpretationCreate] = Field(default_factory=list)
    scoring_rules:   Optional[ScoringRulesV1]   = None


class PreviewAnswerIn(BaseModel):
    """
    Ответ в предпросмотре. Вопросы адресуются по question_order, а варианты по
    option_order, а не по id: дерево ещё не сохранено и id у него нет.
    """
    question_order:         int
    option_order:           Optional[int]       = None
    selected_option_orders: Optional[list[int]] = None
    scale_value:            Optional[int]       = None
    free_text_answer:       Optional[str]       = None


class TestPreviewScoreIn(TestAnalyzeIn):
    answers: list[PreviewAnswerIn] = Field(default_factory=list)


class ScoreBoundsRead(BaseModel):
    scale_name: Optional[str]     # None = итоговый балл одношкального теста
    min_score:  int
    max_score:  int


class InterpretationIssueRead(BaseModel):
    scale_name: Optional[str]
    min_score:  int
    max_score:  int
    kind:       str               # gap | out_of_range | unknown_scale
    label:      Optional[str] = None


class RuleIssueRead(BaseModel):
    """ADR-037: несогласованность правил с вопросами. Блокирует отправку на
    проверку и публикацию (422), в черновике — предупреждение."""
    kind:       Literal["scale_missing", "scale_unused", "level_gap", "norm_gap"]
    scale_name: str
    min_score:  Optional[int] = None
    max_score:  Optional[int] = None
    message:    str


class TestAnalysisRead(BaseModel):
    score_bounds: list[ScoreBoundsRead]
    issues:       list[InterpretationIssueRead]
    rule_issues:  list[RuleIssueRead] = Field(default_factory=list)


class TestRead(BaseModel):
    uuid:           str
    title:          str
    description:    Optional[str]
    version:        int
    scoring:        str
    max_score:      Optional[int]
    time_limit_min: Optional[int]
    is_active:      bool
    status:         str
    shuffle_questions: bool
    shuffle_options:   bool
    scoring_rules:  Optional[dict] = None
    campaign_only:  bool = False
    lineage_uuid:   Optional[str] = None       # ADR-037: общий для версий
    superseded_at:  Optional[datetime] = None  # вышла новая опубликованная версия
    created_at:     datetime
    updated_at:     datetime
    created_by_name: Optional[str]
    categories:     list[CategoryRef]
    tags:           list[TagRef]
    questions:      list[QuestionRead]
    interpretations: list[InterpretationRead]


class TestListItem(BaseModel):
    """Облегчённый объект для таблицы в админке."""
    uuid:            str
    title:           str
    scoring:         str
    version:         int
    is_active:       bool
    status:          str
    question_count:  int
    categories:      list[CategoryRef]
    tags:            list[TagRef]
    created_at:      datetime
    created_by_name: Optional[str]
    # Токен версии для решений модерации (expected_updated_at): меняется при
    # каждой правке и смене статуса.
    updated_at:      Optional[datetime] = None
    # ADR-037: вышла более новая опубликованная версия; «только по ссылке».
    superseded_at:   Optional[datetime] = None
    campaign_only:   bool = False


class PaginatedTestsResponse(BaseModel):
    items: list[TestListItem]
    total: int
    page:  int
    size:  int


# ── moderation workflow (Этап F) ──────────────────────────────────────────────

class TestPendingCountOut(BaseModel):
    """GET /api/admin/tests/pending-count: только число (бейдж меню)."""
    count: int


ModerationStatus = Literal["draft", "in_review", "needs_changes", "published"]


class _TextOptionIn(BaseModel):
    model_config = {"extra": "forbid"}
    option_order: int
    option_text:  str = Field(min_length=1, max_length=2000)

    @field_validator("option_text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("пустой текст")
        return v


class _TextQuestionIn(BaseModel):
    model_config = {"extra": "forbid"}
    question_order: int
    question_text:  str = Field(min_length=1, max_length=5000)
    options:        list[_TextOptionIn] = Field(default_factory=list)

    @field_validator("question_text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("пустой текст")
        return v


class TestTextsIn(BaseModel):
    """ADR-037: исправление опечаток без смены структуры. Состав вопросов и
    вариантов — ровно как в методике; меняются только тексты и инструкция
    (ключ instruction не передан — не менять)."""
    model_config = {"extra": "forbid"}
    expected_updated_at: datetime
    questions:   list[_TextQuestionIn] = Field(max_length=1000)
    instruction: Optional[str] = Field(default=None, max_length=2000)


class TestDecisionIn(BaseModel):
    """
    Решение модерации по конкретному состоянию теста (ADR-016, дополнение
    2026-11-02): статус и updated_at, которые видел проверяющий. Если под
    блокировкой состояние другое — 409 test_state_changed без изменений.
    expected_status = in_review — решение по проверке; draft/needs_changes —
    намеренная прямая публикация.
    """
    expected_status:     ModerationStatus
    expected_updated_at: datetime

    model_config = {"extra": "forbid"}


class TestReturnIn(TestDecisionIn):
    """Возврат теста на доработку (in_review → needs_changes). reason необязателен —
    свободный текст в response не логируется (audit metadata пустая)."""
    reason: Optional[str] = Field(default=None, max_length=2000)


# ── student-facing (Этап B) ───────────────────────────────────────────────────

class TestPublicListItem(BaseModel):
    uuid:           str
    title:          str
    description:    Optional[str]
    time_limit_min: Optional[int]
    question_count: int
    categories:     list[CategoryRef]
    tags:           list[TagRef]


class PaginatedPublicTestsResponse(BaseModel):
    items: list[TestPublicListItem]
    total: int
    page:  int
    size:  int


class TakeOptionRead(BaseModel):
    """Вариант для прохождения — БЕЗ value_score (ключ теста не раскрывается)."""
    id:           int
    option_text:  str
    option_order: int
    media:        list[MediaOut] = Field(default_factory=list)


class TakeQuestionRead(BaseModel):
    id:             int
    question_text:  str
    question_order: int
    question_type:  str
    is_required:    bool
    config:         dict
    media:          list[MediaOut] = Field(default_factory=list)
    options:        list[TakeOptionRead]


class TestTakeRead(BaseModel):
    uuid:           str
    title:          str
    description:    Optional[str]
    time_limit_min: Optional[int]
    questions:      list[TakeQuestionRead]


class AnswerIn(BaseModel):
    question_id:      int
    option_id:        Optional[int]       = None
    selected_options: Optional[list[int]] = None
    scale_value:      Optional[int]       = None
    free_text_answer: Optional[str]       = None
    time_spent_sec:   Optional[int]       = Field(default=None, ge=0)


class SubmitIn(BaseModel):
    answers: list[AnswerIn] = Field(default_factory=list)
    # Клиентский тайм-лимит: при истечении фронт авто-отправляет то, что успели
    # ответить. Тогда проверка обязательности пропускается (неотвеченные вопросы
    # дают 0), иначе частичные ответы потерялись бы на 422. Флаг клиентский
    # (не защита от обмана): позволяет студенту лишь досрочно сдать с пропусками.
    timed_out: bool = False


class ScaleResultRead(BaseModel):
    scale_name:     str
    score:          int
    max_score:      Optional[int]
    interpretation: Optional[str]
    label:          Optional[str]


class TestPreviewScoreRead(BaseModel):
    """
    Результат пробного подсчёта в конструкторе. Тот же расчёт, что у студента
    (scoring.compute_result), но ничего не сохраняется: ни test_results,
    ни student_answers, ни uuid.
    """
    total_score:     Optional[int]
    max_possible:    Optional[int]
    scoring_used:    str
    recommendations: Optional[str]
    scales:          list[ScaleResultRead]
    # ADR-037: по правилам — уровень основных шкал, достоверность и типы.
    levels:          dict[str, Optional[str]] = Field(default_factory=dict)
    rule_summary:    Optional["RuleSummaryRead"] = None


class ResultRead(BaseModel):
    uuid:            str
    test_uuid:       Optional[str]
    test_title:      Optional[str]
    total_score:     Optional[int]
    max_possible:    Optional[int]
    scoring_used:    Optional[str]
    recommendations: Optional[str]
    submitted_at:    datetime
    scales:          list[ScaleResultRead]


class RuleSummaryRead(BaseModel):
    """ADR-037: снимок правил на момент отправки. None у is_valid — у методики
    нет правила достоверности."""
    is_valid: Optional[bool]
    types:    list[str]


class StaffResultRead(ResultRead):
    """Деталь результата для психолога/супервизора (Этап E): плюс снимок
    достоверности и типов и подписи шкал из правил методики (ADR-037)."""
    rule_summary: Optional[RuleSummaryRead] = None
    scale_labels: dict[str, str] = Field(default_factory=dict)


class ResultListItem(BaseModel):
    uuid:         str
    test_uuid:    Optional[str]
    test_title:   Optional[str]
    total_score:  Optional[int]
    max_possible: Optional[int]
    submitted_at: datetime


class PaginatedResultsResponse(BaseModel):
    items: list[ResultListItem]
    total: int
    page:  int
    size:  int


# ── staff-доступ к результатам (Этап E) ───────────────────────────────────────

class StaffResultListItem(BaseModel):
    """Metadata результата студента для staff — БЕЗ баллов (баллы только в
    detail под audit)."""
    uuid:         str
    test_title:   Optional[str]
    submitted_at: datetime


class PaginatedStaffResultsResponse(BaseModel):
    items: list[StaffResultListItem]
    total: int
    page:  int
    size:  int


class StaffAnswerOptionRead(BaseModel):
    """Выбранный вариант: текст (то же имя, что у варианта при прохождении) и
    его медиа. value_score/id не отдаются — ключ теста скрыт."""
    option_text: str
    media:       list[MediaOut]


class StaffAnswerItemRead(BaseModel):
    """Вопрос теста и сохранённый ответ клиента. answered=False — «Нет ответа»."""
    position:      int
    question_text: str
    question_type: str
    answered:      bool
    media:         list[MediaOut]
    options:       list[StaffAnswerOptionRead]
    scale_value:   Optional[int]
    scale_min:     Optional[int]
    scale_max:     Optional[int]
    free_text:     Optional[str]


class StaffResultAnswersRead(BaseModel):
    """
    Ответы прохождения для психолога клиента (ADR-016, дополнение 2026-10-29).
    test_title — АКТУАЛЬНОЕ название теста (snapshot нет); ответы — сохранённые
    значения. order="test_order": вопросы в порядке теста, фактический порядок
    показа клиенту (перемешивание) не сохраняется.
    """
    result_uuid:  str
    test_title:   Optional[str]
    submitted_at: datetime
    order:        Literal["test_order"]
    items:        list[StaffAnswerItemRead]


class ConsentStatusRead(BaseModel):
    policy_type: str
    version:     int
    title:       str
    content:     str
    accepted:    bool


# Ссылка вперёд на RuleSummaryRead (ADR-037).
TestPreviewScoreRead.model_rebuild()
