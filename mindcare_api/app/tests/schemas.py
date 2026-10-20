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

from pydantic import BaseModel, Field

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


class TestAnalysisRead(BaseModel):
    score_bounds: list[ScoreBoundsRead]
    issues:       list[InterpretationIssueRead]


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


class PaginatedTestsResponse(BaseModel):
    items: list[TestListItem]
    total: int
    page:  int
    size:  int


# ── moderation workflow (Этап F) ──────────────────────────────────────────────

class TestReturnIn(BaseModel):
    """Возврат теста на доработку (in_review → needs_changes). reason необязателен —
    свободный текст в response не логируется (audit metadata пустая)."""
    reason: Optional[str] = None


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


class ConsentStatusRead(BaseModel):
    policy_type: str
    version:     int
    title:       str
    content:     str
    accepted:    bool
