"""
Pydantic-схемы модуля психодиагностики (Этап A — admin CRUD конструктора теста).

Тест редактируется как единая вложенная структура: тест + вопросы + варианты +
пороги интерпретации. Это соответствует UI-конструктору (одна форма — один сабмит).

MVP-ограничения (см. docs/MODULES/psychodiagnostics-spec-draft.md):
  - scoring: только sum / average (enum БД допускает weighted/custom — позже);
  - question_type: single_choice / multiple_choice / scale / free_text
    (free_text хранится, но в скоринг не входит).
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# MVP-подмножества enum'ов БД
ScoringMethod = Literal["sum", "average"]
QuestionType  = Literal["single_choice", "multiple_choice", "scale", "free_text"]


# ── вложенные create-схемы ────────────────────────────────────────────────────

class OptionCreate(BaseModel):
    option_text:  str = Field(min_length=1)
    option_order: int = Field(ge=0)
    value_score:  int = 0


class QuestionCreate(BaseModel):
    question_text:  str           = Field(min_length=1)
    question_order: int           = Field(ge=0)
    question_type:  QuestionType  = "single_choice"
    is_required:    bool          = True
    config:         dict          = Field(default_factory=dict)
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


class OptionRead(BaseModel):
    id:           int
    option_text:  str
    option_order: int
    value_score:  int


class QuestionRead(BaseModel):
    id:             int
    question_text:  str
    question_order: int
    question_type:  str
    is_required:    bool
    config:         dict
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


class TakeQuestionRead(BaseModel):
    id:             int
    question_text:  str
    question_order: int
    question_type:  str
    is_required:    bool
    config:         dict
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


class ConsentStatusRead(BaseModel):
    policy_type: str
    version:     int
    title:       str
    content:     str
    accepted:    bool
